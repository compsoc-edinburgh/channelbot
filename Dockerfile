FROM python:3

RUN mkdir /usr/src/app
WORKDIR /usr/src/app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]
