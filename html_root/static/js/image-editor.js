// static/js/image-editor.js - 图片编辑器（裁剪等功能）

let cropperInstance = null;
let currentImageId = null;
let currentContext = null; // 'agent' 或 'canvas'
let originalFile = null;
let isApplyingEdit = false; // 标志：是否正在应用编辑，防止重复打开编辑器
let editorJustClosed = false; // 标志：编辑器是否刚刚关闭，防止立即重新打开

/**
 * 获取 Cropper 构造函数（处理加载时序问题）
 */
function getCropper() {
    // 尝试从全局获取 Cropper
    if (typeof window !== 'undefined' && window.Cropper) {
        return window.Cropper;
    }
    if (typeof Cropper !== 'undefined') {
        return Cropper;
    }
    return null;
}

/**
 * 等待 Cropper.js 加载完成
 */
function waitForCropper(maxRetries = 10, delay = 100) {
    return new Promise((resolve, reject) => {
        let retries = 0;
        const checkCropper = () => {
            const Cropper = getCropper();
            if (Cropper) {
                resolve(Cropper);
            } else if (retries < maxRetries) {
                retries++;
                setTimeout(checkCropper, delay);
            } else {
                reject(new Error('Cropper.js 未加载，请刷新页面重试'));
            }
        };
        checkCropper();
    });
}

/**
 * 打开图片编辑器
 * @param {string} imageId - 图片元素的 ID
 * @param {string} context - 上下文：'agent' 或 'canvas'
 */
export function openEditor(imageId, context) {
    // 如果编辑器刚刚关闭或正在应用编辑，阻止打开
    if (editorJustClosed || isApplyingEdit) {
        console.log('Editor just closed or applying edit, skipping auto-open');
        return;
    }
    
    const img = document.getElementById(imageId);
    
    currentImageId = imageId;
    currentContext = context;
    editorJustClosed = false; // 重置标志

    const modal = document.getElementById('image-editor-modal');
    const previewImg = document.getElementById('image-editor-preview');
    const loadingEl = document.getElementById('image-editor-loading');

    if (!modal || !previewImg) {
        console.warn('openEditor: modal or preview element not found');
        return;
    }

    // 获取图片源
    let imageSrc = null;
    
    if (context === 'canvas') {
        // 画板页面：优先从预览图获取，如果没有则从 canvas 获取
        if (img && img.src) {
            imageSrc = img.src;
        } else {
            // 从 canvas 获取图片数据
            const canvas = document.getElementById('drawing-board');
            if (canvas) {
                imageSrc = canvas.toDataURL('image/png');
                // 更新预览图的 src，以便编辑器使用
                if (img) {
                    img.src = imageSrc;
                }
            }
        }
        // 确保预览图容器显示（用于编辑器）
        const previewContainer = document.getElementById('uploaded-preview-container');
        if (previewContainer && img && img.src) {
            previewContainer.style.display = 'block';
            if (img) img.style.display = 'block';
        }
    } else {
        // 智能体页面：直接使用预览图的 src
        if (!img || !img.src) {
            console.warn('openEditor: image element or src missing', imageId);
            return;
        }
        imageSrc = img.src;
    }
    
    if (!imageSrc) {
        console.warn('openEditor: no valid image source found');
        return;
    }

    // 显示模态框
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    // 显示加载指示
    if (loadingEl) loadingEl.style.display = 'flex';

    // 清理旧的 cropper
    if (cropperInstance) {
        cropperInstance.destroy();
        cropperInstance = null;
    }

    // 重置预览图
    previewImg.onload = null;
    previewImg.onerror = null;
    previewImg.src = '';
    previewImg.style.display = 'block';

    // 设置图片并在加载后初始化 Cropper
    previewImg.onload = async () => {
        if (loadingEl) loadingEl.style.display = 'none';

        // 再次销毁旧实例（保险起见）
        if (cropperInstance) {
            try {
                cropperInstance.destroy();
            } catch (_) {}
            cropperInstance = null;
        }

        // 等待 Cropper.js 加载完成
        try {
            const Cropper = await waitForCropper();
            
            // 确保图片元素可见且已加载
            if (!previewImg.complete || previewImg.naturalWidth === 0) {
                console.warn('Image not fully loaded, waiting...');
                return;
            }

            cropperInstance = new Cropper(previewImg, {
                aspectRatio: NaN, // 自由比例
                viewMode: 1,
                dragMode: 'move',
                autoCropArea: 0.8,
                restore: false,
                guides: true,
                center: true,
                highlight: true,
                cropBoxMovable: true,
                cropBoxResizable: true,
                toggleDragModeOnDblclick: false,
                responsive: true,
                ready: function() {
                    // Cropper 初始化完成后的回调
                    console.log('Cropper initialized successfully');
                }
            });
        } catch (e) {
            console.error('Cropper init error:', e);
            if (loadingEl) loadingEl.style.display = 'none';
            if (typeof showToast === 'function') {
                showToast('图片编辑器加载失败，请刷新页面重试', 'error');
            }
            // 关闭编辑器
            closeEditor();
        }
    };

    previewImg.onerror = () => {
        console.error('Failed to load image for editor');
        if (loadingEl) loadingEl.style.display = 'none';
        if (typeof showToast === 'function') {
            showToast('图片加载失败，请重试', 'error');
        }
    };

    previewImg.src = imageSrc;

    // 记录原始文件（用于 applyEdit 时构造 File 名称）
    if (context === 'agent') {
        if (window.Agent && window.Agent.getAttachedFile) {
            originalFile = window.Agent.getAttachedFile() || null;
        } else {
            originalFile = null;
        }
    } else if (context === 'canvas') {
        const fileInput = document.getElementById('image-upload');
        originalFile = (fileInput && fileInput.files && fileInput.files[0]) || null;
    } else if (context === 'devtools-latex') {
        const fileInput = document.getElementById('dev-latex-image');
        originalFile = (fileInput && fileInput.files && fileInput.files[0]) || null;
    } else {
        originalFile = null;
    }
}

/**
 * 关闭图片编辑器
 */
export function closeEditor() {
    const modal = document.getElementById('image-editor-modal');
    const previewImg = document.getElementById('image-editor-preview');
    const loadingEl = document.getElementById('image-editor-loading');

    // 先清理 cropper 实例
    if (cropperInstance) {
        try {
            cropperInstance.destroy();
        } catch (_) {}
        cropperInstance = null;
    }

    // 清理加载状态
    if (loadingEl) loadingEl.style.display = 'none';

    // 清理预览图的事件监听器和内容
    if (previewImg) {
        previewImg.onload = null;
        previewImg.onerror = null;
        previewImg.src = '';
        previewImg.style.display = 'none';
    }

    // 隐藏模态框
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }

    // 设置标志：编辑器刚刚关闭，防止立即重新打开
    editorJustClosed = true;
    // 2秒后重置标志（足够长的时间防止自动打开）
    setTimeout(() => {
        editorJustClosed = false;
    }, 2000);

    // 清理状态变量（延迟清理，以便 applyEdit 可以使用）
    setTimeout(() => {
        currentImageId = null;
        currentContext = null;
        originalFile = null;
    }, 100);
}

/**
 * 应用编辑结果
 */
export function applyEdit() {
    if (!cropperInstance || !currentImageId) {
        if (typeof showToast === 'function') {
            showToast('编辑器未初始化，请重试', 'error');
        }
        return;
    }

    // 设置标志：正在应用编辑
    isApplyingEdit = true;

    // 保存上下文信息，因为 closeEditor 会清空它们
    const savedContext = currentContext;
    const savedImageId = currentImageId;
    const savedFileName = (originalFile && originalFile.name) || 'edited-image.jpg';

    let canvas;
    try {
        canvas = cropperInstance.getCroppedCanvas({
            imageSmoothingEnabled: true,
            imageSmoothingQuality: 'high'
        });
    } catch (e) {
        console.error('Failed to get cropped canvas:', e);
        isApplyingEdit = false; // 重置标志
        if (typeof showToast === 'function') {
            showToast('获取裁剪结果失败，请重试', 'error');
        }
        return;
    }
    
    if (!canvas) {
        isApplyingEdit = false; // 重置标志
        if (typeof showToast === 'function') {
            showToast('裁剪失败，请重试', 'error');
        }
        return;
    }

    canvas.toBlob((blob) => {
        if (!blob) {
            isApplyingEdit = false; // 重置标志
            return;
        }

        const img = document.getElementById(savedImageId);
        const file = new File([blob], savedFileName, { type: blob.type || 'image/jpeg' });

        // 先关闭编辑器，防止后续操作触发自动打开
        closeEditor();

        // 延迟更新图片，确保编辑器已完全关闭
        setTimeout(() => {
            if (img) {
                const url = URL.createObjectURL(blob);
                img.src = url;
            }

            if (savedContext === 'agent') {
                if (window.Agent && window.Agent.updateImagePreview) {
                    // 传递 skipAutoOpen=true 防止移动端再次自动打开编辑器
                    window.Agent.updateImagePreview(file, true);
                }
            } else if (savedContext === 'canvas') {
                const fileInput = document.getElementById('image-upload');
                if (fileInput) {
                    const dt = new DataTransfer();
                    dt.items.add(file);
                    fileInput.files = dt.files;
                    window.dispatchEvent(new CustomEvent('recognition-source-change'));
                    if (window.handleImageFile) {
                        // 传递 skipAutoOpen=true 防止移动端再次自动打开编辑器
                        window.handleImageFile(file, true);
                    }
                }
            } else if (savedContext === 'devtools-latex') {
                const fileInput = document.getElementById('dev-latex-image');
                if (fileInput) {
                    const dt = new DataTransfer();
                    dt.items.add(file);
                    fileInput.files = dt.files;
                }
            }

            // 重置标志：编辑应用完成
            setTimeout(() => {
                isApplyingEdit = false;
            }, 500); // 再延迟500ms确保所有操作完成
        }, 200); // 增加延迟到200ms
    }, 'image/jpeg', 0.95);
}

// 导出到全局，供 HTML 调用
window.ImageEditor = {
    openEditor,
    closeEditor,
    applyEdit,
    // 导出标志供外部检查
    get _editorJustClosed() {
        return editorJustClosed;
    },
    get _isApplyingEdit() {
        return isApplyingEdit;
    }
};
