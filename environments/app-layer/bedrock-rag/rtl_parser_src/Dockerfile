# AWS Lambda Python 3.12 Base Image (ECR 마이그레이션 대비)
# 향후 PyVerilog + Icarus Verilog 의존성이 Lambda Layer 250MB 제한 초과 시 사용
FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py .

CMD ["handler.handler"]
