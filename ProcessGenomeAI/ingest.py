import os

from dotenv import load_dotenv

from langchain_community.document_loaders import PyPDFLoader

from langchain.text_splitter import RecursiveCharacterTextSplitter

from langchain_openai import AzureOpenAIEmbeddings

from langchain_community.vectorstores import FAISS


load_dotenv()


PDF_PATH="documents"


def create_vector_store():


    documents=[]


    for file in os.listdir(PDF_PATH):

        if file.endswith(".pdf"):

            loader=PyPDFLoader(
                f"{PDF_PATH}/{file}"
            )

            documents.extend(
                loader.load()
            )


    print(
        "Pages loaded:",
        len(documents)
    )


    splitter=RecursiveCharacterTextSplitter(

        chunk_size=1000,

        chunk_overlap=200

    )


    chunks=splitter.split_documents(
        documents
    )


    print(
        "Chunks created:",
        len(chunks)
    )


    embeddings=AzureOpenAIEmbeddings(

        azure_deployment=
        "text-embedding-3-large"

    )


    db=FAISS.from_documents(

        chunks,

        embeddings

    )


    db.save_local(
        "vectorstore"
    )


    print(
        "Vector database created"
    )



if __name__=="__main__":

    create_vector_store()
