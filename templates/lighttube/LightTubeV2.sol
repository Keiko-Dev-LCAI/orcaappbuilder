// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title  LightTubeV2
 * @notice Public video platform on Lightchain AI.
 *         Supports two upload paths:
 *
 *         ① DIRECT  — user's wallet signs every transaction (small/test files only)
 *         ② RELAY   — relay wallet submits on behalf of user (all sizes, no gas for user)
 *
 *         For relay uploads:
 *           1. User signs a plain message off-chain (no gas, one click)
 *           2. Relay calls initVideoFor(uploader, ...) → videoId
 *           3. Relay calls addVideoChunkFor(videoId, i, chunkData) × N
 *           Events record the REAL user wallet as uploader, not the relay wallet.
 *
 * Network:  Lightchain AI Mainnet  |  Chain ID: 9200
 */
contract LightTubeV2 {

    // ─────────────────────────────────────────────────────────────────
    //  STORAGE
    // ─────────────────────────────────────────────────────────────────

    struct VideoMeta {
        address uploader;
        uint256 totalChunks;
        bool    exists;
    }

    mapping(uint256 => VideoMeta) public videos;
    uint256 public nextVideoId = 1;

    address public owner;
    address public relayWallet;

    // ─────────────────────────────────────────────────────────────────
    //  CONSTRUCTOR & ADMIN
    // ─────────────────────────────────────────────────────────────────

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier onlyRelay() {
        require(relayWallet != address(0), "Relay not configured");
        require(msg.sender == relayWallet, "Not relay wallet");
        _;
    }

    /// @notice Set the relay wallet address (owner only, one-time or updatable)
    function setRelayWallet(address _relay) external onlyOwner {
        require(_relay != address(0), "Zero address");
        relayWallet = _relay;
    }

    // ─────────────────────────────────────────────────────────────────
    //  EVENTS  (identical to V1 for full frontend compatibility)
    // ─────────────────────────────────────────────────────────────────

    event VideoUploaded(
        uint256 indexed videoId,
        address indexed uploader,
        string  title,
        string  description,
        string  category,
        string  dataURI,
        uint256 timestamp
    );

    event VideoCreated(
        uint256 indexed videoId,
        address indexed uploader,
        string  title,
        string  description,
        string  category,
        uint256 totalChunks,
        uint256 timestamp
    );

    event VideoChunkStored(
        uint256 indexed videoId,
        uint256 indexed chunkIndex,
        uint256 totalChunks,
        string  chunkData
    );

    // ─────────────────────────────────────────────────────────────────
    //  DIRECT UPLOAD  (user wallet, small files / testing)
    // ─────────────────────────────────────────────────────────────────

    function uploadVideo(
        string memory title,
        string memory description,
        string memory category,
        string memory dataURI
    ) external {
        uint256 id = nextVideoId++;
        emit VideoUploaded(id, msg.sender, title, description, category, dataURI, block.timestamp);
    }

    function initVideo(
        string memory title,
        string memory description,
        string memory category,
        uint256 totalChunks
    ) external returns (uint256) {
        require(totalChunks > 0, "totalChunks must be >= 1");
        uint256 id = nextVideoId++;
        videos[id] = VideoMeta(msg.sender, totalChunks, true);
        emit VideoCreated(id, msg.sender, title, description, category, totalChunks, block.timestamp);
        return id;
    }

    function addVideoChunk(
        uint256 videoId,
        uint256 chunkIndex,
        string calldata chunkData
    ) external {
        require(videos[videoId].exists,                          "Video not found");
        require(videos[videoId].uploader == msg.sender,          "Not video uploader");
        require(chunkIndex < videos[videoId].totalChunks,        "Chunk index out of range");
        emit VideoChunkStored(videoId, chunkIndex, videos[videoId].totalChunks, chunkData);
    }

    // ─────────────────────────────────────────────────────────────────
    //  RELAY UPLOAD  (relay wallet submits on behalf of user)
    // ─────────────────────────────────────────────────────────────────

    /// @notice Relay initialises a video on behalf of the real uploader.
    function initVideoFor(
        address uploader,
        string memory title,
        string memory description,
        string memory category,
        uint256 totalChunks
    ) external onlyRelay returns (uint256) {
        require(uploader != address(0), "Invalid uploader address");
        require(totalChunks > 0,         "totalChunks must be >= 1");
        uint256 id = nextVideoId++;
        videos[id] = VideoMeta(uploader, totalChunks, true);
        emit VideoCreated(id, uploader, title, description, category, totalChunks, block.timestamp);
        return id;
    }

    /// @notice Relay uploads one chunk for any existing video.
    function addVideoChunkFor(
        uint256 videoId,
        uint256 chunkIndex,
        string calldata chunkData
    ) external onlyRelay {
        require(videos[videoId].exists,                   "Video not found");
        require(chunkIndex < videos[videoId].totalChunks, "Chunk index out of range");
        emit VideoChunkStored(videoId, chunkIndex, videos[videoId].totalChunks, chunkData);
    }

    // ─────────────────────────────────────────────────────────────────
    //  VIEW
    // ─────────────────────────────────────────────────────────────────

    function getVideoCount() external view returns (uint256) {
        return nextVideoId - 1;
    }
}
