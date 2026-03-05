FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt -t "${LAMBDA_TASK_ROOT}"

COPY title_generator.py "${LAMBDA_TASK_ROOT}/"

CMD ["title_generator.lambda_handler"]
