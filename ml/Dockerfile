# Dockerfile para ML - SAAI Predicción de Demanda
# Usa Holt-Winters (statsmodels) con Python 3.10

FROM public.ecr.aws/lambda/python:3.10

# Copiar requirements y instalar dependencias
COPY ml/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copiar código ML
COPY ml/entrenar_modelos.py ${LAMBDA_TASK_ROOT}/
COPY ml/generar_predicciones_por_tienda.py ${LAMBDA_TASK_ROOT}/
COPY ml/prediccion_demanda.py ${LAMBDA_TASK_ROOT}/
COPY ml/config.py ${LAMBDA_TASK_ROOT}/
COPY ml/utils_ml.py ${LAMBDA_TASK_ROOT}/

# Copiar utils compartidos del proyecto
COPY utils ${LAMBDA_TASK_ROOT}/utils/
COPY constants.py ${LAMBDA_TASK_ROOT}/

# Handler por defecto (se sobrescribe en serverless.yml)
CMD ["entrenar_modelos.handler"]
