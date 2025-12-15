const express = require("express");
const axios = require("axios");

const router = express.Router();

router.post("/", async (req, res) => {
  const response = await axios.post("http://127.0.0.1:8000/render", req.body);
  res.json(response.data);
});

module.exports = router;
