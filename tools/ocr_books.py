"""第 0 步(只在电脑上运行, 可选): 把 data/raw 里的扫描版 PDF 词汇书 OCR 成文字, 给 parse_books.py 用

依赖(只在这一步要, 不进 requirements.txt, 建议单独的虚拟环境):  pip install pymupdf rapidocr-onnxruntime
运行:  python tools/ocr_books.py [最多识别几页, 默认全部]      例如先跑 50 页试试, 随时可以 Ctrl+C 停
输出:  data/work/ocr/<书>/0001.json    每页一个文件, 内容 [[x, y, 宽, 高, 置信度, 文字], ...]
       已经有的页不重复做, 中断后重新运行会接着跑
说明:  PDF 自带的文字层(有的书有)质量很差, 一律重新识别。OCR 会丢变音和空格, 校正在 parse_books.py 里做
       故意跑得慢: 单进程、2 线程、最低优先级、每页歇一下, 这样不影响电脑的正常使用。不要改成多进程
"""
import glob
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "work", "ocr")
BOOKS = {"exam": "Häufig*.pdf", "tem4": "德语专业四级*.pdf", "core": "德语核心词汇*.pdf"}   # 文件名太长, 按开头找
WIDTH = 1000      # 页面缩放到这个宽度再识别: 再大也不更准, 只会更慢
THREADS = 2       # OCR 用几个线程
PAUSE = 1.0       # 每页之间歇几秒, 让 CPU 降下来


def source(book):
    return glob.glob(os.path.join(RAW, BOOKS[book]))[0]


def lower_priority():
    """把自己调成最低优先级: 别的程序要用 CPU 时让给它们"""
    if os.name == "nt":
        import ctypes
        IDLE_PRIORITY_CLASS = 0x40
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetPriorityClass(ctypes.c_void_p(kernel32.GetCurrentProcess()), IDLE_PRIORITY_CLASS)
    else:
        os.nice(19)


def ocr_page(engine, documents, job):
    import fitz
    import numpy as np
    book, n = job
    doc = documents.setdefault(book, fitz.open(source(book)))
    page = doc[n]
    zoom = WIDTH / page.rect.width
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY)
    gray = np.frombuffer(pix.samples, dtype="uint8").reshape(pix.height, pix.stride)[:, :pix.width]
    result, _ = engine(np.stack([gray] * 3, -1))
    boxes = []
    for box, text, conf in result or []:
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        boxes.append([round(min(xs)), round(min(ys)), round(max(xs) - min(xs)), round(max(ys) - min(ys)),
                      round(float(conf), 3), text])
    path = os.path.join(OUT, book, f"{n + 1:04d}.json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(boxes, f, ensure_ascii=False)
    os.replace(path + ".tmp", path)


def main():
    import fitz
    from rapidocr_onnxruntime import RapidOCR
    sys.stdout.reconfigure(encoding="utf-8")
    lower_priority()
    jobs = []
    for book in BOOKS:
        os.makedirs(os.path.join(OUT, book), exist_ok=True)
        pages = len(fitz.open(source(book)))
        jobs += [(book, n) for n in range(pages)
                 if not os.path.exists(os.path.join(OUT, book, f"{n + 1:04d}.json"))]
    print(f"还要识别 {len(jobs)} 页", flush=True)
    if len(sys.argv) > 1:
        jobs = jobs[:int(sys.argv[1])]
    engine = RapidOCR(intra_op_num_threads=THREADS, inter_op_num_threads=1)
    documents = {}
    for done, job in enumerate(jobs, 1):
        ocr_page(engine, documents, job)
        if done % 20 == 0 or done == len(jobs):
            print(f"  {done}/{len(jobs)}", flush=True)
        time.sleep(PAUSE)


if __name__ == "__main__":
    main()
