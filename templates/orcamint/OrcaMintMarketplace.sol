// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title OrcaMintMarketplace
 * @notice Standalone marketplace for the EXISTING OrcaMint NFT contract on
 *         Lightchain (chainId 9200, LCAI is native coin). Replaces the buggy
 *         marketplace that was bolted into the NFT contract, WITHOUT touching or
 *         migrating any minted NFTs — they stay where they are.
 *
 *   What this fixes vs. the old built-in marketplace:
 *     • Adds cancelOffer(): a buyer can always reclaim an offer's escrowed LCAI
 *       (including after it expires). The old contract had no return path, so
 *       offer funds could sit locked forever.
 *     • Escrowed offer funds are tracked (escrowedOffers) and can NEVER be
 *       swept by the owner's withdraw() — withdraw only takes accrued platform
 *       fees. The old withdraw() drained the entire balance, escrow included.
 *     • Reentrancy guard on every value-moving function; checks-effects-
 *       interactions ordering throughout.
 *
 *   How it operates on existing NFTs:
 *     A seller approves this marketplace on the NFT contract (approve or
 *     setApprovalForAll). Listing/offer acceptance then moves the NFT via the
 *     standard ERC-721 transferFrom. Royalties are read from the NFT's
 *     ERC-2981 royaltyInfo and honored on every sale.
 *
 *   NFT contract: 0xe7bD4500277f6167B6b454CF2CF529c062B4Ca1a
 */

interface IERC721Min {
    function ownerOf(uint256 tokenId) external view returns (address);
    function transferFrom(address from, address to, uint256 tokenId) external;
    function getApproved(uint256 tokenId) external view returns (address);
    function isApprovedForAll(address owner, address operator) external view returns (bool);
}

interface IERC2981Min {
    function royaltyInfo(uint256 tokenId, uint256 salePrice)
        external view returns (address receiver, uint256 amount);
}

contract OrcaMintMarketplace {

    IERC721Min public immutable nft;
    address public owner;
    uint256 public platformBps = 250; // 2.5%

    // Total LCAI currently escrowed for open offers. withdraw() can NEVER touch
    // this — it belongs to buyers until an offer is accepted or cancelled.
    uint256 public escrowedOffers;

    struct Listing { address seller; uint256 price; }
    struct Offer   { address buyer;  uint256 amount; uint256 expiresAt; }

    mapping(uint256 => Listing)  public listings;
    mapping(uint256 => Offer[])  public offers;

    modifier onlyOwner() { require(msg.sender == owner, "Not owner"); _; }

    uint256 private _reentry = 1;
    modifier nonReentrant() {
        require(_reentry == 1, "Reentrant call");
        _reentry = 2;
        _;
        _reentry = 1;
    }

    event Listed(uint256 indexed tokenId, address indexed seller, uint256 price);
    event Unlisted(uint256 indexed tokenId);
    event Sold(uint256 indexed tokenId, address indexed seller, address indexed buyer, uint256 price);
    event OfferMade(uint256 indexed tokenId, address indexed buyer, uint256 amount);
    event OfferAccepted(uint256 indexed tokenId, address indexed seller, address indexed buyer, uint256 amount);
    event OfferCancelled(uint256 indexed tokenId, address indexed buyer, uint256 amount);

    constructor(address nftAddress) {
        nft = IERC721Min(nftAddress);
        owner = msg.sender;
    }

    // ── internal: does this marketplace have permission to move the token? ──
    function _approved(uint256 tokenId, address holder) internal view returns (bool) {
        return nft.getApproved(tokenId) == address(this)
            || nft.isApprovedForAll(holder, address(this));
    }

    // ── internal: pay platform fee + royalty, return what the seller nets ──
    function _payout(uint256 tokenId, uint256 price, address seller) internal returns (uint256 sellerGets) {
        uint256 platformCut = price * platformBps / 10000;
        uint256 royaltyCut;
        address royaltyReceiver;
        try IERC2981Min(address(nft)).royaltyInfo(tokenId, price) returns (address r, uint256 a) {
            royaltyReceiver = r;
            royaltyCut = a;
        } catch { royaltyCut = 0; }
        if (royaltyReceiver == seller || royaltyReceiver == address(0)) royaltyCut = 0;
        if (royaltyCut + platformCut > price) { royaltyCut = 0; } // safety: never overspend

        sellerGets = price - platformCut - royaltyCut;
        if (platformCut > 0) payable(owner).transfer(platformCut);
        if (royaltyCut > 0)  payable(royaltyReceiver).transfer(royaltyCut);
        payable(seller).transfer(sellerGets);
    }

    // ─────────────── Listings ───────────────

    function listForSale(uint256 tokenId, uint256 price) external {
        require(nft.ownerOf(tokenId) == msg.sender, "Not owner");
        require(price > 0, "Price must be > 0");
        require(_approved(tokenId, msg.sender), "Approve marketplace first");
        listings[tokenId] = Listing(msg.sender, price);
        emit Listed(tokenId, msg.sender, price);
    }

    function unlist(uint256 tokenId) external {
        require(listings[tokenId].seller == msg.sender, "Not seller");
        delete listings[tokenId];
        emit Unlisted(tokenId);
    }

    function buy(uint256 tokenId) external payable nonReentrant {
        Listing memory l = listings[tokenId];
        require(l.price > 0, "Not for sale");
        require(msg.value >= l.price, "Insufficient payment");
        require(msg.sender != l.seller, "Cannot buy own NFT");
        require(nft.ownerOf(tokenId) == l.seller, "Listing stale");

        uint256 price = l.price;
        address seller = l.seller;
        delete listings[tokenId];               // effects before interactions

        nft.transferFrom(seller, msg.sender, tokenId);
        _payout(tokenId, price, seller);

        if (msg.value > price) payable(msg.sender).transfer(msg.value - price);
        emit Sold(tokenId, seller, msg.sender, price);
    }

    // ─────────────── Offers ───────────────

    function makeOffer(uint256 tokenId, uint256 expiresAt) external payable nonReentrant {
        require(msg.value > 0, "Offer must be > 0");
        require(expiresAt > block.timestamp, "Expiry must be in future");
        nft.ownerOf(tokenId); // reverts if token does not exist
        offers[tokenId].push(Offer(msg.sender, msg.value, expiresAt));
        escrowedOffers += msg.value;
        emit OfferMade(tokenId, msg.sender, msg.value);
    }

    function acceptOffer(uint256 tokenId, uint256 offerIndex) external nonReentrant {
        require(nft.ownerOf(tokenId) == msg.sender, "Not owner");
        require(_approved(tokenId, msg.sender), "Approve marketplace first");
        Offer memory o = offers[tokenId][offerIndex];
        require(o.amount > 0, "Invalid offer");
        require(block.timestamp <= o.expiresAt, "Offer expired");

        uint256 price = o.amount;
        address buyer = o.buyer;

        // effects before interactions
        uint256 last = offers[tokenId].length - 1;
        if (offerIndex != last) offers[tokenId][offerIndex] = offers[tokenId][last];
        offers[tokenId].pop();
        escrowedOffers -= price;
        delete listings[tokenId]; // if it was also listed, clear it

        nft.transferFrom(msg.sender, buyer, tokenId);
        _payout(tokenId, price, msg.sender);
        emit OfferAccepted(tokenId, msg.sender, buyer, price);
    }

    /**
     * @notice Reclaim your own offer and get your escrowed LCAI back.
     * @dev Callable by the buyer any time before acceptance, including after
     *      the offer expires. This is the return path the old contract lacked.
     */
    function cancelOffer(uint256 tokenId, uint256 offerIndex) external nonReentrant {
        Offer memory o = offers[tokenId][offerIndex];
        require(o.buyer == msg.sender, "Not your offer");
        require(o.amount > 0, "Invalid offer");

        uint256 refund = o.amount;
        uint256 last = offers[tokenId].length - 1;
        if (offerIndex != last) offers[tokenId][offerIndex] = offers[tokenId][last];
        offers[tokenId].pop();
        escrowedOffers -= refund;

        payable(msg.sender).transfer(refund);
        emit OfferCancelled(tokenId, msg.sender, refund);
    }

    function getOffers(uint256 tokenId) external view returns (Offer[] memory) {
        return offers[tokenId];
    }

    // ─────────────── Admin ───────────────

    function setPlatformBps(uint256 bps) external onlyOwner { require(bps <= 1000, "Max 10%"); platformBps = bps; }
    function transferOwnership(address newOwner) external onlyOwner { require(newOwner != address(0), "Zero"); owner = newOwner; }

    /// @notice Sweep accrued platform fees only. Buyer escrow is never touched.
    function withdraw() external onlyOwner {
        uint256 free = address(this).balance - escrowedOffers;
        require(free > 0, "Nothing to withdraw");
        payable(owner).transfer(free);
    }
}
