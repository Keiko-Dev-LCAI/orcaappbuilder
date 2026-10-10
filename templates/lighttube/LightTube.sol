// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title  LightTube
 * @notice Public video platform on Lightchain AI.
 *         Videos are stored permanently as base64 data URIs in EVM event logs.
 *         No IPFS, no servers, no algorithms, no takedowns — ever.
 *
 *         Two upload paths:
 *
 *         ① SMALL videos (base64 ≤ 1MB)
 *            uploadVideo(title, description, category, dataURI)
 *            One transaction. Emits VideoUploaded.
 *
 *         ② LARGE videos (base64 > 1MB)
 *            initVideo(title, description, category, totalChunks) → videoId
 *            addVideoChunk(videoId, 0, chunk0)
 *            addVideoChunk(videoId, 1, chunk1)
 *            ...
 *            Frontend reassembles by sorting VideoChunkStored events by
 *            chunkIndex and concatenating chunkData strings.
 *
 * Network:  Lightchain AI Mainnet  |  Chain ID: 9200
 * RPC:      https://rpc.mainnet.lightchain.ai
 * Deploy:   https://remix.ethereum.org  (MetaMask, Chrome, VPN ON)
 */
contract LightTube {

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

    // ─────────────────────────────────────────────────────────────────
    //  EVENTS
    // ─────────────────────────────────────────────────────────────────

    /// @notice Emitted when a small video is uploaded in one transaction.
    event VideoUploaded(
        uint256 indexed videoId,
        address indexed uploader,
        string  title,
        string  description,
        string  category,
        string  dataURI,
        uint256 timestamp
    );

    /// @notice Emitted when a large video upload is initialised.
    event VideoCreated(
        uint256 indexed videoId,
        address indexed uploader,
        string  title,
        string  description,
        string  category,
        uint256 totalChunks,
        uint256 timestamp
    );

    /// @notice Emitted for each chunk of a large video.
    event VideoChunkStored(
        uint256 indexed videoId,
        uint256 indexed chunkIndex,
        uint256 totalChunks,
        string  chunkData
    );

    // ─────────────────────────────────────────────────────────────────
    //  FUNCTIONS
    // ─────────────────────────────────────────────────────────────────

    /**
     * @notice Upload a small video in one transaction (base64 ≤ 1MB).
     * @param title       Video title
     * @param description Video description
     * @param category    Category string (e.g. "Music", "Family", "Education")
     * @param dataURI     Full base64 data URI of the video
     */
    function uploadVideo(
        string memory title,
        string memory description,
        string memory category,
        string memory dataURI
    ) external {
        uint256 id = nextVideoId++;
        emit VideoUploaded(id, msg.sender, title, description, category, dataURI, block.timestamp);
    }

    /**
     * @notice Initialise a large video upload.
     *         Call once, then call addVideoChunk() for each chunk.
     * @param title       Video title
     * @param description Video description
     * @param category    Category string
     * @param totalChunks Total number of chunks to be uploaded
     * @return videoId    Assigned ID for this video
     */
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

    /**
     * @notice Upload one chunk of a large video.
     * @param videoId    The ID returned by initVideo()
     * @param chunkIndex Zero-based chunk index
     * @param chunkData  Slice of the complete base64 data URI string
     */
    function addVideoChunk(
        uint256 videoId,
        uint256 chunkIndex,
        string calldata chunkData
    ) external {
        require(videos[videoId].exists,                "Video not found");
        require(videos[videoId].uploader == msg.sender, "Not video uploader");
        require(chunkIndex < videos[videoId].totalChunks, "Chunk index out of range");
        emit VideoChunkStored(videoId, chunkIndex, videos[videoId].totalChunks, chunkData);
    }

    /**
     * @notice Returns total number of videos ever uploaded.
     */
    function getVideoCount() external view returns (uint256) {
        return nextVideoId - 1;
    }
}
