FROM python:3.8

ENV PYTHONBUFFERED 1

ENV CODE_WEBSERVER /code

RUN apt-get update && apt-get install -y default-mysql-client

# Add code from src folder
WORKDIR ${CODE_WEBSERVER}
ADD . ${CODE_WEBSERVER}

# Install requirements
RUN pip install -q -r requirements.txt

# Include entrypoint
ADD docker/entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

EXPOSE 8000

VOLUME ["/job_logs"]
VOLUME ["/spdx_files"]

ENTRYPOINT ["/entrypoint.sh"]
