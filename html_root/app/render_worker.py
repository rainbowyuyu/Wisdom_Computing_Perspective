"""Launch Manim under per-process Linux limits, including its TeX/FFmpeg children."""
import os
import runpy
import sys


def main():
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        os.environ[key]='1'
    if sys.platform.startswith('linux'):
        import resource
        try:memory=max(256,min(2048,int(os.getenv('MANIM_WORKER_MEMORY_MB','768'))))*1024*1024
        except ValueError:memory=768*1024*1024
        resource.setrlimit(resource.RLIMIT_AS,(memory,memory))
        resource.setrlimit(resource.RLIMIT_CPU,(240,245))
        resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024*1024,128*1024*1024))
        os.nice(10)
    # Keep the CLI and output layout identical to python -m manim.
    sys.argv[0]='manim'
    runpy.run_module('manim',run_name='__main__')


if __name__=='__main__':main()
