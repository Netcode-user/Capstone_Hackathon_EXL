import os
from dotenv import load_dotenv


load_dotenv()


AZURE_OPENAI_API_KEY=os.getenv(
    "AZURE_OPENAI_API_KEY"
)


AZURE_OPENAI_ENDPOINT=os.getenv(
    "AZURE_OPENAI_ENDPOINT"
)


API_VERSION=os.getenv(
    "AZURE_OPENAI_API_VERSION"
)


CHAT_MODEL=os.getenv(
    "AZURE_OPENAI_CHAT_DEPLOYMENT"
)


EMBEDDING_MODEL=os.getenv(
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
)
