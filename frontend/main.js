const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");

ctx.lineWidth = 3;
ctx.lineCap = "round";
let drawing = false;

canvas.onmousedown = () => drawing = true;
canvas.onmouseup = () => drawing = false;
canvas.onmousemove = e => {
  if (!drawing) return;
  ctx.lineTo(e.offsetX, e.offsetY);
  ctx.stroke();
};

function clearCanvas() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
}

async function submitCanvas() {
  const blob = await new Promise(r => canvas.toBlob(r));
  const formData = new FormData();
  formData.append("image", blob);

  const res = await fetch("http://localhost:3000/api/detect", {
    method: "POST",
    body: formData
  });

  const data = await res.json();
  document.getElementById("latexResult").value = data.latex;
  document.getElementById("latexView").innerHTML = `$$${data.latex}$$`;
  MathJax.typeset();
}

async function renderAnimation() {
  const latex = document.getElementById("latexResult").value;

  const res = await fetch("http://localhost:3000/api/render", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ latex })
  });

  const data = await res.json();
  document.getElementById("video").src = data.video;
}
