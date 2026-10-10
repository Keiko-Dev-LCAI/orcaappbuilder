// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title  LightTubeV3
 * @notice Adds on-chain metadata editing to LightTubeV2.
 *
 *         New in V3:
 *           - videoUploader mapping stored for ALL upload paths (enables on-chain ownership checks)
 *           - updateMetadata()      — original uploader can edit title / description / category
 *           - VideoMetadataUpdated — full edit history recorded on-chain, newest entry wins
 *
 *         All V2 functionality preserved (relay upload, direct upload, chunked upload).
 *         V2 relay functions identical — existing relay server works with no changes.
 *
 * Network:  Lightchain AI Mainnet  |  Chain ID: 9200
 */
contract LightTubeV3 {

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
        require(msg.sender == relayWallet,  "Not relay wallet");
        _;
    }

    /// @notice Set the relay wallet address (owner only)
    function setRelayWallet(address _relay) external onlyOwner {
        require(_relay != address(0), "Zero address");
        relayWallet = _relay;
    }

    // ─────────────────────────────────────────────────────────────────
    //  EVENTS
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

    /// @notice NEW in V3 — emitted whenever an uploader edits their video metadata.
    ///         Full history is on-chain; the frontend uses the most recent event per videoId.
    event VideoMetadataUpdated(
        uint256 indexed videoId,
        address indexed uploader,
        string  title,
        string  description,
        string  category,
        uint256 timestamp
    );

    // ─────────────────────────────────────────────────────────────────
    //  DIRECT UPLOAD  (user wallet signs every transaction)
    // ─────────────────────────────────────────────────────────────────

    function uploadVideo(
        string memory title,
        string memory description,
        string memory category,
        string memory dataURI
    ) external {
        uint256 id = nextVideoId++;
        videos[id] = VideoMeta(msg.sender, 1, true);   // V3 fix: store uploader for small files too
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
        require(videos[videoId].exists,                   "Video not found");
        require(videos[videoId].uploader == msg.sender,   "Not video uploader");
        require(chunkIndex < videos[videoId].totalChunks, "Chunk index out of range");
        emit VideoChunkStored(videoId, chunkIndex, videos[videoId].totalChunks, chunkData);
    }

    // ─────────────────────────────────────────────────────────────────
    //  RELAY UPLOAD  (relay wallet submits on behalf of real user)
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
    //  NEW IN V3: METADATA EDITING
    // ─────────────────────────────────────────────────────────────────

    /// @notice Edit your video's title, description, or category.
    ///         Only the original uploader can call this.
    ///         Emits VideoMetadataUpdated — the full edit history lives on-chain forever.
    function updateMetadata(
        uint256 videoId,
        string memory title,
        string memory description,
        string memory category
    ) external {
        require(videos[videoId].exists,                 "Video not found");
        require(videos[videoId].uploader == msg.sender, "Not video uploader");
        emit VideoMetadataUpdated(videoId, msg.sender, title, description, category, block.timestamp);
    }

    // ─────────────────────────────────────────────────────────────────
    //  VIEW
    // ─────────────────────────────────────────────────────────────────

    function getVideoCount() external view returns (uint256) {
        return nextVideoId - 1;
    }
}
