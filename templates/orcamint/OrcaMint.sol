// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title OrcaMint
 * @notice First NFT minting platform on Lightchain.
 *
 *   Features:
 *     • ERC-721 NFT minting with metadata URI
 *     • ERC-2981 creator royalties (set at mint, paid forever on resales)
 *     • Built-in marketplace: list, buy, offer, accept
 *     • Collections (group NFTs into themed sets)
 *     • Art origin labels: 0=Artist Upload, 1=AIVM Enhanced, 2=AIVM Generated
 *     • Platform mint fee (LCAI) → owner
 *     • Platform commission on sales (2.5%) → owner
 *     • Scam/hidden NFT support (owner can hide spam)
 *
 *   Pricing:
 *     • Mint:     mintFee LCAI (default: 1 LCAI, owner can update)
 *     • Create collection: collectionFee LCAI (default: 5 LCAI)
 *     • Sale:     2.5% platform fee + creator royalty (set by minter, 0–20%)
 *
 * @dev Deployed on Lightchain mainnet (chainId 9200). LCAI is native coin.
 */
contract OrcaMint {

    // ─────────────────────────────────────────────
    //  ERC-165
    // ─────────────────────────────────────────────

    function supportsInterface(bytes4 interfaceId) public pure returns (bool) {
        return interfaceId == 0x80ac58cd // ERC-721
            || interfaceId == 0x5b5e139f // ERC-721Metadata
            || interfaceId == 0x2a55205a // ERC-2981
            || interfaceId == 0x01ffc9a7; // ERC-165
    }

    // ─────────────────────────────────────────────
    //  ERC-721 State
    // ─────────────────────────────────────────────

    string public name   = "OrcaMint";
    string public symbol = "ORCA";

    mapping(uint256 => address) private _owners;
    mapping(address => uint256) private _balances;
    mapping(uint256 => address) private _tokenApprovals;
    mapping(address => mapping(address => bool)) private _operatorApprovals;
    mapping(uint256 => string)  private _tokenURIs;

    uint256 private _nextTokenId = 1;

    // ─────────────────────────────────────────────
    //  ERC-2981 Royalties
    // ─────────────────────────────────────────────

    struct RoyaltyInfo {
        address receiver;
        uint96  bps; // basis points out of 10000 (e.g. 500 = 5%)
    }
    mapping(uint256 => RoyaltyInfo) private _royalties;

    function royaltyInfo(uint256 tokenId, uint256 salePrice)
        public view returns (address receiver, uint256 amount)
    {
        RoyaltyInfo memory r = _royalties[tokenId];
        return (r.receiver, salePrice * r.bps / 10000);
    }

    // ─────────────────────────────────────────────
    //  Collections
    // ─────────────────────────────────────────────

    struct Collection {
        uint256 id;
        address creator;
        string  name;
        string  description;
        string  imageURI;
        uint256 maxSupply;   // 0 = unlimited
        uint256 mintCount;
        uint256 mintPrice;   // per-collection mint price (0 = use global mintFee)
        uint256 launchAt;    // unix timestamp (0 = live now)
        bool    exists;
    }

    mapping(uint256 => Collection) public collections;
    mapping(uint256 => uint256)    public tokenCollection; // tokenId → collectionId
    uint256 private _nextCollectionId = 1;

    // ─────────────────────────────────────────────
    //  Art Origin Labels
    // ─────────────────────────────────────────────

    // 0 = Artist Upload, 1 = AIVM Enhanced, 2 = AIVM Generated
    mapping(uint256 => uint8) public tokenOrigin;

    // ─────────────────────────────────────────────
    //  Marketplace
    // ─────────────────────────────────────────────

    struct Listing {
        address seller;
        uint256 price; // in LCAI (wei)
    }
    struct Offer {
        address buyer;
        uint256 amount;
        uint256 expiresAt;
    }

    mapping(uint256 => Listing)   public listings;
    mapping(uint256 => Offer[])   public offers;
    mapping(uint256 => bool)      public hiddenTokens; // spam/scam flagging

    // ─────────────────────────────────────────────
    //  Platform Config
    // ─────────────────────────────────────────────

    address public owner;
    uint256 public mintFee        = 1 ether;   // 1 LCAI
    uint256 public collectionFee  = 5 ether;   // 5 LCAI
    uint256 public platformBps    = 250;        // 2.5%

    modifier onlyOwner() { require(msg.sender == owner, "Not owner"); _; }

    // ─────────────────────────────────────────────
    //  Events
    // ─────────────────────────────────────────────

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);
    event Minted(uint256 indexed tokenId, address indexed creator, uint256 collectionId, uint8 origin);
    event CollectionCreated(uint256 indexed collectionId, address indexed creator, string name);
    event Listed(uint256 indexed tokenId, address indexed seller, uint256 price);
    event Unlisted(uint256 indexed tokenId);
    event Sold(uint256 indexed tokenId, address indexed seller, address indexed buyer, uint256 price);
    event OfferMade(uint256 indexed tokenId, address indexed buyer, uint256 amount);
    event OfferAccepted(uint256 indexed tokenId, address indexed seller, address indexed buyer, uint256 amount);

    // ─────────────────────────────────────────────
    //  Constructor
    // ─────────────────────────────────────────────

    constructor() {
        owner = msg.sender;
    }

    // ─────────────────────────────────────────────
    //  ERC-721 Core
    // ─────────────────────────────────────────────

    function balanceOf(address _owner) public view returns (uint256) {
        require(_owner != address(0), "Zero address");
        return _balances[_owner];
    }

    function ownerOf(uint256 tokenId) public view returns (address) {
        address o = _owners[tokenId];
        require(o != address(0), "Token does not exist");
        return o;
    }

    function tokenURI(uint256 tokenId) public view returns (string memory) {
        require(_owners[tokenId] != address(0), "Token does not exist");
        return _tokenURIs[tokenId];
    }

    function approve(address to, uint256 tokenId) public {
        address o = ownerOf(tokenId);
        require(msg.sender == o || isApprovedForAll(o, msg.sender), "Not authorized");
        _tokenApprovals[tokenId] = to;
        emit Approval(o, to, tokenId);
    }

    function getApproved(uint256 tokenId) public view returns (address) {
        require(_owners[tokenId] != address(0), "Token does not exist");
        return _tokenApprovals[tokenId];
    }

    function setApprovalForAll(address operator, bool approved) public {
        _operatorApprovals[msg.sender][operator] = approved;
        emit ApprovalForAll(msg.sender, operator, approved);
    }

    function isApprovedForAll(address _owner, address operator) public view returns (bool) {
        return _operatorApprovals[_owner][operator];
    }

    function _isApprovedOrOwner(address spender, uint256 tokenId) internal view returns (bool) {
        address o = ownerOf(tokenId);
        return spender == o
            || getApproved(tokenId) == spender
            || isApprovedForAll(o, spender);
    }

    function transferFrom(address from, address to, uint256 tokenId) public {
        require(_isApprovedOrOwner(msg.sender, tokenId), "Not authorized");
        _transfer(from, to, tokenId);
    }

    function safeTransferFrom(address from, address to, uint256 tokenId) public {
        transferFrom(from, to, tokenId);
    }

    function safeTransferFrom(address from, address to, uint256 tokenId, bytes memory) public {
        transferFrom(from, to, tokenId);
    }

    function _transfer(address from, address to, uint256 tokenId) internal {
        require(ownerOf(tokenId) == from, "Wrong owner");
        require(to != address(0), "Zero address");
        delete _tokenApprovals[tokenId];
        _balances[from]--;
        _balances[to]++;
        _owners[tokenId] = to;
        // Auto-unlist on transfer
        if (listings[tokenId].price > 0) {
            delete listings[tokenId];
            emit Unlisted(tokenId);
        }
        emit Transfer(from, to, tokenId);
    }

    // ─────────────────────────────────────────────
    //  Minting
    // ─────────────────────────────────────────────

    /**
     * @notice Mint a single NFT.
     * @param to          Recipient wallet
     * @param uri         Metadata JSON as an on-chain base64 data URI (image bytes embedded inline; stored fully on-chain in contract state — no R2/IPFS/servers)
     * @param royaltyBps  Creator royalty in basis points (0–2000, i.e. 0–20%)
     * @param collectionId  Collection to attach to (0 = none)
     * @param origin      0=Artist Upload, 1=AIVM Enhanced, 2=AIVM Generated
     */
    function mint(
        address to,
        string  memory uri,
        uint96  royaltyBps,
        uint256 collectionId,
        uint8   origin
    ) external payable returns (uint256 tokenId) {
        require(royaltyBps <= 2000, "Royalty max 20%");
        require(origin <= 2, "Invalid origin");

        uint256 required = mintFee;
        if (collectionId > 0) {
            Collection storage col = collections[collectionId];
            require(col.exists, "Collection not found");
            require(col.maxSupply == 0 || col.mintCount < col.maxSupply, "Sold out");
            require(block.timestamp >= col.launchAt || col.launchAt == 0, "Not launched yet");
            if (col.mintPrice > 0) required = col.mintPrice;
            col.mintCount++;
        }
        require(msg.value >= required, "Insufficient mint fee");

        tokenId = _nextTokenId++;
        _owners[tokenId]   = to;
        _balances[to]++;
        _tokenURIs[tokenId] = uri;
        _royalties[tokenId] = RoyaltyInfo(to, royaltyBps);
        tokenCollection[tokenId] = collectionId;
        tokenOrigin[tokenId] = origin;

        // Forward mint fee to platform
        if (msg.value > 0) {
            payable(owner).transfer(msg.value);
        }

        emit Transfer(address(0), to, tokenId);
        emit Minted(tokenId, to, collectionId, origin);
    }

    // ─────────────────────────────────────────────
    //  Collections
    // ─────────────────────────────────────────────

    function createCollection(
        string  memory colName,
        string  memory description,
        string  memory imageURI,
        uint256 maxSupply,
        uint256 mintPrice,
        uint256 launchAt
    ) external payable returns (uint256 colId) {
        require(msg.value >= collectionFee, "Insufficient collection fee");

        colId = _nextCollectionId++;
        collections[colId] = Collection({
            id:          colId,
            creator:     msg.sender,
            name:        colName,
            description: description,
            imageURI:    imageURI,
            maxSupply:   maxSupply,
            mintCount:   0,
            mintPrice:   mintPrice,
            launchAt:    launchAt,
            exists:      true
        });

        payable(owner).transfer(msg.value);
        emit CollectionCreated(colId, msg.sender, colName);
    }

    function getCollection(uint256 colId) external view returns (Collection memory) {
        return collections[colId];
    }

    function nextCollectionId() external view returns (uint256) {
        return _nextCollectionId;
    }

    function nextTokenId() external view returns (uint256) {
        return _nextTokenId;
    }

    // ─────────────────────────────────────────────
    //  Marketplace
    // ─────────────────────────────────────────────

    function listForSale(uint256 tokenId, uint256 price) external {
        require(ownerOf(tokenId) == msg.sender, "Not owner");
        require(price > 0, "Price must be > 0");
        listings[tokenId] = Listing(msg.sender, price);
        emit Listed(tokenId, msg.sender, price);
    }

    function unlist(uint256 tokenId) external {
        require(listings[tokenId].seller == msg.sender, "Not seller");
        delete listings[tokenId];
        emit Unlisted(tokenId);
    }

    function buy(uint256 tokenId) external payable {
        Listing memory listing = listings[tokenId];
        require(listing.price > 0, "Not for sale");
        require(msg.value >= listing.price, "Insufficient payment");
        require(msg.sender != listing.seller, "Cannot buy own NFT");

        address seller = listing.seller;
        uint256 price  = listing.price;
        delete listings[tokenId];

        // Calculate splits
        uint256 platformCut = price * platformBps / 10000;
        (address royaltyReceiver, uint256 royaltyCut) = royaltyInfo(tokenId, price);
        // Don't double-pay royalty if seller IS the creator
        if (royaltyReceiver == seller) royaltyCut = 0;
        uint256 sellerGets = price - platformCut - royaltyCut;

        // Pay out
        payable(owner).transfer(platformCut);
        if (royaltyCut > 0) payable(royaltyReceiver).transfer(royaltyCut);
        payable(seller).transfer(sellerGets);

        // Transfer NFT
        _transfer(seller, msg.sender, tokenId);
        emit Sold(tokenId, seller, msg.sender, price);

        // Refund overpayment
        if (msg.value > price) {
            payable(msg.sender).transfer(msg.value - price);
        }
    }

    function makeOffer(uint256 tokenId, uint256 expiresAt) external payable {
        require(_owners[tokenId] != address(0), "Token does not exist");
        require(msg.value > 0, "Offer must be > 0");
        require(expiresAt > block.timestamp, "Expiry must be in future");
        offers[tokenId].push(Offer(msg.sender, msg.value, expiresAt));
        emit OfferMade(tokenId, msg.sender, msg.value);
    }

    function acceptOffer(uint256 tokenId, uint256 offerIndex) external {
        require(ownerOf(tokenId) == msg.sender, "Not owner");
        Offer memory o = offers[tokenId][offerIndex];
        require(o.amount > 0, "Invalid offer");
        require(block.timestamp <= o.expiresAt, "Offer expired");

        uint256 price = o.amount;
        address buyer = o.buyer;

        // Remove offer
        uint256 last = offers[tokenId].length - 1;
        if (offerIndex != last) offers[tokenId][offerIndex] = offers[tokenId][last];
        offers[tokenId].pop();

        // Splits
        uint256 platformCut = price * platformBps / 10000;
        (address royaltyReceiver, uint256 royaltyCut) = royaltyInfo(tokenId, price);
        if (royaltyReceiver == msg.sender) royaltyCut = 0;
        uint256 sellerGets = price - platformCut - royaltyCut;

        payable(owner).transfer(platformCut);
        if (royaltyCut > 0) payable(royaltyReceiver).transfer(royaltyCut);
        payable(msg.sender).transfer(sellerGets);

        _transfer(msg.sender, buyer, tokenId);
        emit OfferAccepted(tokenId, msg.sender, buyer, price);
    }

    function getOffers(uint256 tokenId) external view returns (Offer[] memory) {
        return offers[tokenId];
    }

    // ─────────────────────────────────────────────
    //  Admin
    // ─────────────────────────────────────────────

    function setMintFee(uint256 fee)       external onlyOwner { mintFee = fee; }
    function setCollectionFee(uint256 fee) external onlyOwner { collectionFee = fee; }
    function setPlatformBps(uint256 bps)   external onlyOwner { require(bps <= 1000, "Max 10%"); platformBps = bps; }
    function hideToken(uint256 tokenId, bool hidden) external onlyOwner { hiddenTokens[tokenId] = hidden; }
    function transferOwnership(address newOwner) external onlyOwner { owner = newOwner; }
    function withdraw() external onlyOwner { payable(owner).transfer(address(this).balance); }
}
