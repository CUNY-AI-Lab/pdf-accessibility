FROM public.ecr.aws/lambda/nodejs:22

# Install native build deps for better-sqlite3 and sharp, plus sqlite runtime
RUN dnf install -y python3 make gcc gcc-c++ sqlite-libs && dnf clean all

COPY package*.json "${LAMBDA_TASK_ROOT}/"
RUN cd "${LAMBDA_TASK_ROOT}" && npm install --omit=dev

COPY *.js "${LAMBDA_TASK_ROOT}/"

CMD ["alt_text_generator.handler"]
