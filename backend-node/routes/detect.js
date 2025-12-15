const express = require("express");
const multer = require("multer");
const axios = require("axios");
const fs = require("fs");

const router = express.Router();
const upload = multer({ dest: "uploads/" });

router.post("/", upload.single("image"), async (req, res) => {
  const response = await axios.post("http://127.0.0.1:8000/detect", {
    path: req.file.path
  });
  res.json(response.data);
});

module.exports = router;
