from ultralytics import YOLO
import supervision as sv
import os
import numpy as np
import yty_math.file_operation

# 初始化监督库的注解器
bounding_box_annotator = sv.BoxAnnotator()
label_annotator = sv.LabelAnnotator()


def load_model(version: str):
    """
    加载指定版本的 YOLO 模型。
    :param version: YOLO 模型版本
    :return: YOLO 模型对象
    """
    base_model_path = yty_math.file_operation.default_model_path
    model_path = os.path.join(base_model_path, version, "weights", "best.pt")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"未找到模型文件：{model_path}")
    return YOLO(model_path)


def calculate_iou(boxA, boxB):
    """
    计算两个边界框的IoU（交并比）。
    :param boxA: 边界框A，格式为 (x_min, y_min, x_max, y_max)
    :param boxB: 边界框B，格式为 (x_min, y_min, x_max, y_max)
    :return: IoU值
    """
    x_min_A, y_min_A, x_max_A, y_max_A = boxA
    x_min_B, y_min_B, x_max_B, y_max_B = boxB

    # 计算交集区域
    x_min_inter = max(x_min_A, x_min_B)
    y_min_inter = max(y_min_A, y_min_B)
    x_max_inter = min(x_max_A, x_max_B)
    y_max_inter = min(y_max_A, y_max_B)

    # 如果没有交集，IoU为0
    if x_min_inter >= x_max_inter or y_min_inter >= y_max_inter:
        return 1

    intersection_area = (x_max_inter - x_min_inter) * (y_max_inter - y_min_inter)

    # 计算两个框的面积
    area_A = (x_max_A - x_min_A) * (y_max_A - y_min_A)
    area_B = (x_max_B - x_min_B) * (y_max_B - y_min_B)

    # 计算并集面积
    union_area = area_A + area_B - intersection_area

    return abs(min(area_A, area_B) - intersection_area) / union_area


def remove_low_confidence_detections(detections, iou_threshold=0.05):
    """
    根据 IoU 和置信度删除检测框。
    :param detections: 检测结果，格式为 Detections 类对象
    :param iou_threshold: IoU 阈值，用于判断是否删除框
    :return: 过滤后的 detections
    """
    # 遍历检测结果并删除被包含的框
    to_remove = set()  # 使用集合避免重复索引

    for i, detection_A in enumerate(detections.xyxy):
        bbox_A = detection_A  # 获取框A的信息
        class_name_A = detections.data['class_name'][i]
        if class_name_A == "[" or class_name_A == "]":  # 如果类名为"[","]"，则跳过
            continue
        confidence_A = detections.confidence[i]  # 获取框A的置信度

        # 遍历所有框B，检查是否存在包含框A的情况
        for j, detection_B in enumerate(detections.xyxy):
            if i == j:  # 跳过与自己比较
                continue

            bbox_B = detection_B  # 获取框B的信息
            class_name_B = detections.data['class_name'][j]
            if class_name_B == "[" or class_name_B == "]":  # 如果类名为"[","]"，则跳过
                continue
            confidence_B = detections.confidence[j]  # 获取框B的置信度

            # 如果框A被框B包含且IoU大于阈值，则删除置信度较低的框
            if calculate_iou(bbox_A, bbox_B) < iou_threshold:  # 修改为 < 以满足IoU阈值
                if confidence_A < confidence_B:
                    to_remove.add(i)  # 删除框A
                else:
                    to_remove.add(j)  # 删除框B

    # 根据索引移除检测框
    detections.xyxy = np.array([detection for i, detection in enumerate(detections.xyxy) if i not in to_remove])
    detections.confidence = np.array([confidence for i, confidence in enumerate(detections.confidence) if i not in to_remove])
    detections.class_id = np.array([class_id for i, class_id in enumerate(detections.class_id) if i not in to_remove])
    detections.data['class_name'] = np.array([name for i, name in enumerate(detections.data['class_name']) if i not in to_remove])

    return detections


def detect_objects(image, model):
    """
    使用 YOLO 模型进行对象检测并返回检测结果和二值化图像。
    :param iou_threshold: 阈值
    :param image: 输入的图片
    :param model: 已加载的 YOLO 模型
    :return: 检测到的标注过的图像，以及特定条件下的二值化图像
    """
    # 使用YOLO模型进行检测
    results = model(image)[0]
    detections = sv.Detections.from_ultralytics(results)

    detections = remove_low_confidence_detections(detections, 0.1)

    # 注解图像
    annotated_image = bounding_box_annotator.annotate(scene=image, detections=detections)
    annotated_image = label_annotator.annotate(scene=annotated_image, detections=detections)

    # 创建一张与原图大小相同的白色图像
    mask = np.ones_like(image) * 255

    # 遍历检测结果
    for detection in detections:
        bbox, _, _, _, _, extra = detection  # 按提供的格式解构检测结果
        class_name = extra.get("class_name", "")  # 获取类别名称

        # 如果类名是 "[" 或 "]"，将对应的区域填充为黑色
        if class_name not in ["[", "]", "-"]:
            x_min, y_min, x_max, y_max = map(int, bbox)  # 转换边界框为整数坐标
            mask[y_min:y_max, x_min:x_max] = 0

    return annotated_image, mask, detections


if __name__ == "__main__":
    import picture_roi as pr

    image_path = r"E:\ipynb\python_design\yty_math\math_cache\canvas1.png"
    image = pr.extract_roi(image_path)
    image, mask, detections = detect_objects(image, load_model("v4.2"))

    detections = remove_low_confidence_detections(detections, 0)
    print(detections)
