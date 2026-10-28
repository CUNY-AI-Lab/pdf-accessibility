FROM public.ecr.aws/lambda/python:3.12

# Install system dependencies for pikepdf (qpdf) and PyMuPDF
RUN dnf install -y qpdf-libs qpdf-devel gcc python3-devel && dnf clean all

COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt -t "${LAMBDA_TASK_ROOT}"

COPY ai_tagger_processor.py "${LAMBDA_TASK_ROOT}/"
COPY lib/ "${LAMBDA_TASK_ROOT}/lib/"

CMD ["ai_tagger_processor.lambda_handler"]
