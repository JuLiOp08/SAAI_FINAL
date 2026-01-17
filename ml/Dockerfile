# Dockerfile para ML - SAAI Predicción de Demanda
# Usa Holt-Winters (statsmodels) con Python 3.10

FROM public.ecr.aws/lambda/python:3.10

# Copiar requirements y instalar dependencias
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copiar código ML
COPY entrenar_modelos.py ${LAMBDA_TASK_ROOT}/
COPY prediccion_demanda.py ${LAMBDA_TASK_ROOT}/
COPY config.py ${LAMBDA_TASK_ROOT}/
COPY utils_ml.py ${LAMBDA_TASK_ROOT}/

# Copiar utils compartidos del proyecto
COPY ../utils ${LAMBDA_TASK_ROOT}/utils/
COPY ../constants.py ${LAMBDA_TASK_ROOT}/

# Handler por defecto (se sobrescribe en serverless.yml)
CMD ["prediccion_demanda.handler"]
