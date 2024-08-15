import os, json
import boto3
from aws_lambda_powertools import Logger
# from langchain.indexes import VectorstoreIndexCreator
from langchain_community.embeddings import BedrockEmbeddings
from langchain_community.document_loaders import PyPDFLoader
# from langchain_community.vectorstores import FAISS
from langchain_postgres.vectorstores import PGVector
from langchain.text_splitter import RecursiveCharacterTextSplitter



DOCUMENT_TABLE = os.environ["DOCUMENT_TABLE"]
BUCKET = os.environ["BUCKET"]
EMBEDDING_MODEL_ID = os.environ["EMBEDDING_MODEL_ID"]
REGION = os.environ["REGION"]
DATABASE_SECRET_NAME = os.environ["DATABASE_SECRET_NAME"]

s3 = boto3.client("s3")
ddb = boto3.resource("dynamodb")
document_table = ddb.Table(DOCUMENT_TABLE)
logger = Logger()


def set_doc_status(user_id, document_id, status):
    document_table.update_item(
        Key={"userid": user_id, "documentid": document_id},
        UpdateExpression="SET docstatus = :docstatus",
        ExpressionAttributeValues={":docstatus": status},
    )

def get_db_secret():
    sm_client = boto3.client(
        service_name="secretsmanager",
        region_name=REGION,
    )
    response = sm_client.get_secret_value(
        SecretId=DATABASE_SECRET_NAME
    )["SecretString"]
    secret = json.loads(response)
    return secret


@logger.inject_lambda_context(log_event=True)
def lambda_handler(event, context):
    event_body = json.loads(event["Records"][0]["body"])
    document_id = event_body["documentid"]
    user_id = event_body["user"]
    key = event_body["key"]
    file_name_full = key.split("/")[-1]

    set_doc_status(user_id, document_id, "PROCESSING")

    s3.download_file(BUCKET, key, f"/tmp/{file_name_full}")

    loader = PyPDFLoader(f"/tmp/{file_name_full}")
    data = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=10000, chunk_overlap=1000)
    split_document = text_splitter.split_documents(data)

    bedrock_runtime = boto3.client(
        service_name="bedrock-runtime",
        region_name=REGION,
    )

    embeddings = BedrockEmbeddings(
        model_id=EMBEDDING_MODEL_ID,
        client=bedrock_runtime,
        region_name=REGION,
    )

    ''' OLD CODE
    index_creator = VectorstoreIndexCreator(
        vectorstore_cls=FAISS,
        embedding=embeddings,
    )

    index_from_loader = index_creator.from_loaders([loader])

    index_from_loader.vectorstore.save_local("/tmp")

    s3.upload_file(
        "/tmp/index.faiss", BUCKET, f"{user_id}/{file_name_full}/index.faiss"
    )
    s3.upload_file("/tmp/index.pkl", BUCKET, f"{user_id}/{file_name_full}/index.pkl")
    '''

    collection_name = 'document_collection'
    db_secret = get_db_secret()

    vector_store = PGVector(
        embeddings=embeddings,
        collection_name=collection_name,
        connection=f"postgresql+psycopg2://{db_secret['username']}:{db_secret['password']}@{db_secret['host']}:5432/{db_secret['dbname']}?sslmode=require",
        use_jsonb=True,
    )

    vector_store.add_documents(split_document)

    set_doc_status(user_id, document_id, "READY")
