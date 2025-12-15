const express = require("express");
const cors = require("cors");

const detectRouter = require("./routes/detect");
const renderRouter = require("./routes/render");

const app = express();
app.use(cors());
app.use(express.json());

app.use("/api/detect", detectRouter);
app.use("/api/render", renderRouter);

app.listen(3000, () => {
  console.log("Node 服务启动：http://localhost:3000");
});
