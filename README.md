![logo.png](yty_math/logo.png)


## rainbow_yu 🐋✨

---

### 使用方法


#### 网页访问
- 本项目网页发布于 [智算视界](https://animatecal-aesrxwe852bslylhgvrfxx.streamlit.app/visualize_calculation)


#### 本地部署
1. 配置latex环境
- 如果您有latex环境可跳过此步骤
- 详细下载请参考 [texlive](https://tug.org/texlive/)

2. 配置ghostscript环境
- 如果您有ghostscript环境或不需要使用tk调试界面可跳过此步骤
- 详细下载请参考 [ghostscript](https://www.ghostscript.com/)

3. 配置ffmpeg环境
- 如果您有ffmpeg环境可跳过此步骤
- 详细下载请参考 [ffmpeg](https://ffmpeg.org/)

> ⚠ 注意配置第1,2,3步的环境变量

4. 配置基础环境
- windows
```bash
  cd animate_cal
  pip install -r requirements.txt 
```

- docker
```bash
  docker -pull fufuqaq/ytytest02
```

5. 运行项目
- 本地部署localhost网页
```bash
   streamlit run yty_math/input_window_streamlit.py 
```

- 可视化调试tk界面
```bash
   python yty_math/app.py 
```

- 纯命令行操作
```bash
   python start.py --cal_func det
```
> 这里cal_func参数提供多个选择 det, add, mul 

---

### 文件结构
models  
├── ultralytics  
│   ├── train.py  
│   └── generate_train_v3.ipynb  
└── model  
    ├── v4.2  
    │     ├── weights  
    │     ├── cufusion_matrix  
    │     └── F1_score  
    └──...(其他版本)  

yty_math  
├── __init__.py  
├── import_file.py  
├── picture_roi.py  
├── yolo_detection.py  
├── dbscan_line.py  
├── get_number.py  
├── CA.py  
├── import_window.py  
├── cacl_window.py  
└── yty_canvas.py  
  
yty_manim  
├── __init__.py  
├── squ_tex.py  
├── yty_matrix.py  
├── manim_animation.py  
└── manim_result  