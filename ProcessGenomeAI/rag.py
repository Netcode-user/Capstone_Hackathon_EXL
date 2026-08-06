from dotenv import load_dotenv

from langchain_openai import AzureChatOpenAI

from langchain_openai import AzureOpenAIEmbeddings

from langchain_community.vectorstores import FAISS


load_dotenv()



embeddings = AzureOpenAIEmbeddings(

azure_deployment="text-embedding-3-large"

)



db = FAISS.load_local(

"vectorstore",

embeddings,

allow_dangerous_deserialization=True

)



retriever=db.as_retriever(

search_kwargs={"k":3}

)



llm=AzureChatOpenAI(

azure_deployment="gpt-4o",

temperature=0

)



def ask_processgenome(question):


    docs=retriever.invoke(
        question
    )


    context="\n\n".join(

        [
        d.page_content
        for d in docs
        ]

    )


    prompt=f"""

You are ProcessGenome AI.

You are an IT process expert.

Use the SOP context below.


CONTEXT:

{context}


QUESTION:

{question}


Provide:

1. Answer

2. Process improvement

3. Compliance risks

4. Automation opportunities

"""


    response=llm.invoke(prompt)


    return response.content
