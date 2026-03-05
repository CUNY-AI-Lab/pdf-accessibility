FROM public.ecr.aws/lambda/python:3.12

# Install system dependencies for pikepdf (qpdf) and PyMuPDF
RUN dnf install -y qpdf-libs qpdf-devel gcc python3-devel && dnf clean all

COPY requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt -t "${LAMBDA_TASK_ROOT}"

COPY main.py "${LAMBDA_TASK_ROOT}/"
COPY pdf_accessibility_checker.py "${LAMBDA_TASK_ROOT}/"

CMD ["main.lambda_handler"]
