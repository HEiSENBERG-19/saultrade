# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN apt-get update && apt-get install -y tzdata redis-tools && \
    pip install --no-cache-dir -r requirements.txt

# Install the wheel file
COPY NorenRestApi-0.0.30-py2.py3-none-any.whl /app/NorenRestApi-0.0.30-py2.py3-none-any.whl
RUN pip install --no-cache-dir /app/NorenRestApi-0.0.30-py2.py3-none-any.whl

# Make port 80 available to the world outside this container
EXPOSE 80

# Define environment variable
ENV NAME=World
ENV TZ=Asia/Kolkata

# Run app.py when the container launches with verbose logging
CMD ["python", "-u", "simulation.py"]