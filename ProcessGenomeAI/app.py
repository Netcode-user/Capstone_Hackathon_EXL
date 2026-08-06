import streamlit as st

from rag import ask_processgenome



st.set_page_config(

page_title="ProcessGenome AI",

layout="wide"

)



st.title(
"🧬 ProcessGenome AI - IT Operations"
)



st.write(
"AI powered Dynamic SOP Evolution Platform"
)



question=st.text_input(

"Ask about IT process"

)



if question:


    with st.spinner(
        "Analyzing SOP..."
    ):


        answer=ask_processgenome(
            question
        )


        st.subheader(
        "AI Recommendation"
        )


        st.write(
        answer
        )



st.sidebar.title(
"Process Metrics"
)



st.sidebar.metric(

"Process Health",

"87%"

)



st.sidebar.metric(

"Compliance",

"92%"

)



st.sidebar.metric(

"Automation Potential",

"High"

)
