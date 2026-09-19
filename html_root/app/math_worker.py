"""Trusted, data-only math operations. No web app, database or provider imports."""
import json
import math
import sys


def main():
    request=json.loads(sys.stdin.buffer.read(2_000_001))
    # Linux deployments get hard CPU/address-space limits as well as the parent's
    # wall-clock deadline. Windows uses the same disposable-process deadline.
    if sys.platform.startswith('linux'):
        import resource
        memory=int(request['memory_mb'])*1024*1024
        resource.setrlimit(resource.RLIMIT_AS,(memory,memory))
        cpu=max(1,math.ceil(float(request['timeout'])))
        resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu+1))
    try:
        from app.solution_models import Solution
        from logic.solution_engine import local_solution,resolve_visual_functions,validate_summary_consistency
        from logic.curriculum import exact_example,worked_solution
        from logic.solution_adaptation import parse_solution,verify_parameter_analysis
        data=request['data'];operation=request['operation']
        if operation=='local':result=exact_example(data['problem']) or local_solution(data['problem'])
        elif operation=='example':result=worked_solution(data['example'])
        elif operation=='prepare_ai':
            result=parse_solution(data['content']);validate_summary_consistency(result)
            result.source='ai';result.verification='AI 推导与图形数据，未经符号计算验证；请核对题目条件和结论。'
            if result.completion=='solved':result=verify_parameter_analysis(result,data['problem'])
            result=resolve_visual_functions(result)
        else:raise ValueError('不支持的计算任务')
        output={'result':result.model_dump(mode='json') if isinstance(result,Solution) else None}
    except MemoryError:output={'error':'resource'}
    except (ValueError,SyntaxError,TypeError,NotImplementedError,OverflowError) as error:
        output={'error':'invalid','message':str(error)[:800]}
    sys.stdout.write(json.dumps(output,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':main()
