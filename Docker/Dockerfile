FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV HOTEL_HOST=0.0.0.0
ENV HOTEL_PORT=4180
EXPOSE 4180

CMD ["sh", "-c", "python src/seed_data.py && exec python src/hotel_booking_python_app.py"]
