// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * LightTunesV1 — Permanent, decentralized music hosting on Lightchain AI.
 * Songs are stored as base64-encoded chunks on-chain, assembled by the frontend.
 * Relay wallet handles gas on behalf of uploaders (Trust Wallet sign-once flow).
 */
contract LightTunesV1 {

    address public owner;
    address public relayWallet;
    uint256 public songCount;

    struct Song {
        address uploader;   // original artist wallet
        string  title;
        string  artist;     // display name (optional, defaults to wallet)
        string  genre;      // e.g. "Hip-Hop", "Rock", "Spoken Word"
        string  description;// includes ||album:Name|| ||track:N|| ||explicit|| tags
        bool    isPublic;   // false = private playlist only
        uint256 totalChunks;
        uint256 timestamp;
    }

    mapping(uint256 => Song) public songs;

    // ── Events ──────────────────────────────────────────────────────────────
    event SongCreated(
        uint256 indexed songId,
        address indexed uploader,
        string  title,
        string  artist,
        string  genre,
        string  description,
        bool    isPublic,
        uint256 totalChunks,
        uint256 timestamp
    );

    event SongChunkStored(
        uint256 indexed songId,
        uint256 indexed chunkIndex,
        uint256 totalChunks,
        string  chunkData
    );

    event SongMetadataUpdated(
        uint256 indexed songId,
        address indexed uploader,
        string  title,
        string  artist,
        string  genre,
        string  description,
        bool    isPublic,
        uint256 timestamp
    );

    // ── Access control ───────────────────────────────────────────────────────
    modifier onlyOwner()  { require(msg.sender == owner,       "Not owner");  _; }
    modifier onlyRelay()  { require(msg.sender == relayWallet, "Not relay");  _; }

    constructor() {
        owner      = msg.sender;
        relayWallet = msg.sender; // updated after deploy via setRelayWallet()
    }

    function setRelayWallet(address _relay) external onlyOwner {
        relayWallet = _relay;
    }

    function transferOwnership(address _new) external onlyOwner {
        owner = _new;
    }

    // ── Relay upload (large files — chunked) ─────────────────────────────────
    function initSongFor(
        address uploader,
        string memory title,
        string memory artist,
        string memory genre,
        string memory description,
        bool    isPublic,
        uint256 totalChunks
    ) external onlyRelay returns (uint256) {
        uint256 songId = songCount++;
        songs[songId] = Song(uploader, title, artist, genre, description, isPublic, totalChunks, block.timestamp);
        emit SongCreated(songId, uploader, title, artist, genre, description, isPublic, totalChunks, block.timestamp);
        return songId;
    }

    function addSongChunkFor(
        uint256 songId,
        uint256 chunkIndex,
        string memory chunkData
    ) external onlyRelay {
        Song storage s = songs[songId];
        emit SongChunkStored(songId, chunkIndex, s.totalChunks, chunkData);
    }

    // ── Direct upload (small files — single tx) ──────────────────────────────
    function uploadSong(
        string memory title,
        string memory artist,
        string memory genre,
        string memory description,
        bool    isPublic,
        string memory dataURI
    ) external {
        uint256 songId = songCount++;
        songs[songId] = Song(msg.sender, title, artist, genre, description, isPublic, 1, block.timestamp);
        emit SongCreated(songId, msg.sender, title, artist, genre, description, isPublic, 1, block.timestamp);
        emit SongChunkStored(songId, 0, 1, dataURI);
    }

    // ── Metadata update (uploader or relay only) ─────────────────────────────
    function updateMetadata(
        uint256 songId,
        string memory title,
        string memory artist,
        string memory genre,
        string memory description,
        bool    isPublic
    ) external {
        Song storage s = songs[songId];
        require(msg.sender == s.uploader || msg.sender == relayWallet, "Not authorized");
        s.title       = title;
        s.artist      = artist;
        s.genre       = genre;
        s.description = description;
        s.isPublic    = isPublic;
        emit SongMetadataUpdated(songId, s.uploader, title, artist, genre, description, isPublic, block.timestamp);
    }
}
