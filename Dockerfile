# Use the official Playwright image which has all browsers and dependencies pre-installed
FROM mcr.microsoft.com/playwright/python:v1.52.0-jammy

# Set the working directory inside the container
WORKDIR /app

# Copy only the requirements file to leverage Docker's cache
COPY backend/requirements.txt .

# Install your Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy your entire backend application code into the container
COPY backend/ .

# Expose the port your app will run on. Render uses 10000 for Docker services.
EXPOSE 10000

# The command to run your application using Gunicorn.
# This replaces the "Start Command" from Render's dashboard.
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:10000"]
