import streamlit as st
import boto3
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import time
import mysql.connector
import json
import re
import os
import requests
import csv
from io import StringIO
from botocore.exceptions import ClientError
import logging
from langchain_aws import ChatBedrock
from langchain_core.messages import HumanMessage, AIMessage
from streamlit.web import cli as stcli
from streamlit import runtime
import sys
import pytz

st.set_page_config(layout="wide")

# Session state initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "mode" not in st.session_state:
    st.session_state.mode = "context"
if "context_window" not in st.session_state:
    st.session_state.context_window = 10


# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# 메시지 기록 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 메시지 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

   
# 상태 변수 초기화
if 'show_delete_confirm' not in st.session_state:
    st.session_state.show_delete_confirm = False
if 'show_clone_confirm' not in st.session_state:
    st.session_state.show_clone_confirm = False




# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Session state initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "mode" not in st.session_state:
    st.session_state.mode = "context"
if "context_window" not in st.session_state:
    st.session_state.context_window = 10
if 'show_delete_confirm' not in st.session_state:
    st.session_state.show_delete_confirm = False
if 'show_clone_confirm' not in st.session_state:
    st.session_state.show_clone_confirm = False



def get_available_regions():
    ec2 = boto3.client('ec2')
    regions = [region['RegionName'] for region in ec2.describe_regions()['Regions']]
    return sorted(regions)

def get_running_instances(region):
    ec2 = boto3.client('ec2', region_name=region)
    filters = [{'Name': 'instance-state-name', 'Values': ['running']}]
    response = ec2.describe_instances(Filters=filters)
    instances = []
    
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_info = {
                'InstanceId': instance['InstanceId'],
                'InstanceType': instance['InstanceType'],
                'SubnetId': instance.get('SubnetId', ''),
                'SecurityGroups': instance.get('SecurityGroups', []),
                'ImageId': instance.get('ImageId', ''),
                'Tags': {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
            }
            instances.append(instance_info)
    return instances

col1, col2 = st.columns([1, 4])

with col1:
    st.title("EC2 모니터링")
    
    regions = get_available_regions()
    selected_region = st.selectbox(
        "AWS 리전 선택",
        regions,
        index=regions.index('ap-northeast-2') if 'ap-northeast-2' in regions else 0
    )
    
    instances = get_running_instances(selected_region)
    if instances:
        st.subheader("실행 중인 인스턴스")
        selected_instances = []
        instance_names = {}
        instance_details = {}
        
        for instance in instances:
            instance_name = instance['Tags'].get('Name', 'No Name')
            instance_names[instance['InstanceId']] = instance_name
            instance_details[instance['InstanceId']] = instance
            
            if st.checkbox(f"{instance_name} ({instance['InstanceId']})"):
                selected_instances.append(instance['InstanceId'])
        
        hours = st.slider('조회 기간 (시간)', 1, 24, 1)
        
        # 인스턴스 복제 섹션
        st.subheader("인스턴스 복제")
        num_copies = st.number_input("복제할 인스턴스 수", min_value=1, max_value=10, value=1)
        
        

def clone_instances(region, instance_info, num_copies):
    ec2 = boto3.client('ec2', region_name=region)
    new_instances = []
    print("instance_info:",instance_info)
    print("num_copies:",num_copies)
    try:
        for i in range(num_copies):
            # 기존 인스턴스의 이름 태그 가져오기
            original_name = instance_info['Tags'].get('Name', 'NoName')
            new_name = f"{original_name}-copy{i+1}"
            
            # 인스턴스 생성
            response = ec2.run_instances(
                ImageId=instance_info['ImageId'],
                InstanceType=instance_info['InstanceType'],
                MinCount=1,
                MaxCount=1,
                SubnetId=instance_info['SubnetId'],
                SecurityGroupIds=[sg['GroupId'] for sg in instance_info['SecurityGroups']],
                TagSpecifications=[
                    {
                        'ResourceType': 'instance',
                        'Tags': [
                            {'Key': 'Name', 'Value': new_name},
                            # 기존 태그도 복사
                            *[{'Key': k, 'Value': v} for k, v in instance_info['Tags'].items() if k != 'Name']
                        ]
                    }
                ]
            )
            
            new_instance_id = response['Instances'][0]['InstanceId']
            new_instances.append(new_instance_id)
            
            # 인스턴스가 running 상태가 될 때까지 대기
            waiter = ec2.get_waiter('instance_running')
            waiter.wait(InstanceIds=[new_instance_id])
            
        return new_instances
    except Exception as e:
        st.error(f"인스턴스 생성 중 오류 발생: {str(e)}")
        return []

def get_cpu_info():
    if instances:
        if not selected_instances:
            st.warning("인스턴스를 선택해주세요.")
        else:
            st.title("EC2 CPU 사용률 모니터링")
            with st.spinner("메트릭 데이터를 가져오는 중..."):
                metrics_data = get_ec2_metrics(selected_region, selected_instances, hours)
                fig = plot_all_metrics(metrics_data, instance_names)
                if fig:
                    st.pyplot(fig)
                st.subheader("CPU 사용률 통계")
                stats_df = calculate_statistics(metrics_data)
                if not stats_df.empty:
                    st.dataframe(stats_df, height=400, use_container_width=True)
                else:
                    st.warning("통계 데이터를 가져올 수 없습니다.")

def launch_ec2():
    if 'clone_confirmed' not in st.session_state:
        st.session_state.clone_confirmed = False
 
    if selected_instances:
        st.info(f"다음 인스턴스들을 {num_copies}개씩 복제할까요?")
        for instance_id in selected_instances:
            st.write(f"- {instance_names[instance_id]} ({instance_id})")
            
        col1, col2 = st.columns(2)
        
        def on_confirm_click():
            with st.spinner("인스턴스 복제 중..."):
                for instance_id in selected_instances:
                    new_instances = clone_instances(
                        selected_region,
                        instance_details[instance_id],
                        num_copies
                    )
                    if new_instances:
                        st.success(f"인스턴스 복제 완료: {', '.join(new_instances)}")
            
        with col1:
            st.button("복제 확인", 
                     type="primary", 
                     key="confirm_button", 
                     on_click=on_confirm_click)
                
        with col2:
            if st.button("복제 취소", key="cancel_button"):
                st.session_state.clone_confirmed = False
                st.success("인스턴스 복제가 취소되었습니다")
                return
           
def terminate_ec2():
    if selected_instances:
        st.info(f"다음 인스턴스들을 {num_copies}개씩 삭제할까요?")
        for instance_id in selected_instances:
            st.write(f"- {instance_names[instance_id]} ({instance_id})")

        col1, col2 = st.columns(2)
        
        def on_confirm_click():
            
            with st.spinner("인스턴스 복제 중..."):
                try:
                    ec2 = boto3.client('ec2', region_name=selected_region)
                    ec2.terminate_instances(InstanceIds=selected_instances)
                    return True, "인스턴스 종료 요청이 성공적으로 전송되었습니다."
                except Exception as e:
                    return False, f"인스턴스 종료 중 오류 발생: {str(e)}"  
              
        with col1:
            st.button("삭제 확인", 
                     type="primary", 
                     key="confirm_button", 
                     on_click=on_confirm_click)
                
        with col2:
            if st.button("삭제 취소", key="cancel_button"):
                st.session_state.clone_confirmed = False
                st.success("인스턴스 삭제가 취소되었습니다")
                return




def get_ec2_metrics(region, instance_ids, hours=1):
    cloudwatch = boto3.client('cloudwatch', region_name=region)
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)
    
    metrics_data = {}
    for instance_id in instance_ids:
        response = cloudwatch.get_metric_data(
            MetricDataQueries=[
                {
                    'Id': f'cpu_{instance_id.replace("-", "_")}',
                    'MetricStat': {
                        'Metric': {
                            'Namespace': 'AWS/EC2',
                            'MetricName': 'CPUUtilization',
                            'Dimensions': [{'Name': 'InstanceId', 'Value': instance_id}]
                        },
                        'Period': 300,
                        'Stat': 'Average',
                        'Unit': 'Percent'
                    },
                    'ReturnData': True
                }
            ],
            StartTime=start_time,
            EndTime=end_time
        )
        
        if response['MetricDataResults']:
            metrics_data[instance_id] = {
                'timestamps': response['MetricDataResults'][0]['Timestamps'],
                'values': response['MetricDataResults'][0]['Values']
            }
    
    return metrics_data

def plot_all_metrics(metrics_data, instance_names):
    if not metrics_data:
        return None
    
    fig, ax = plt.subplots(figsize=(8, 4))
    
    for instance_id, data in metrics_data.items():
        if data['timestamps'] and data['values']:
            instance_name = instance_names.get(instance_id, instance_id)
            ax.plot(data['timestamps'], data['values'], label=instance_name)
    
    ax.set_title('CPU Utilization - All Instances')
    ax.set_xlabel('Time')
    ax.set_ylabel('CPU Utilization (%)')
    ax.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    return fig

def calculate_statistics(metrics_data):
    stats = []
    for instance_id, data in metrics_data.items():
        if data['values']:
            stats.append({
                'InstanceId': instance_id,
                'Average CPU': f"{sum(data['values'])/len(data['values']):.2f}%",
                'Max CPU': f"{max(data['values']):.2f}%",
                'Min CPU': f"{min(data['values']):.2f}%"
            })
    return pd.DataFrame(stats)


def interact_with_general_llm(user_request):
    client = boto3.client("bedrock-runtime")
    model_Id = "anthropic.claude-3-sonnet-20240229-v1:0"

    prompt_data = f"""Human: 당신은 AWS EC2 서버관리 전문가입니다. EC2 Linux, Window서버에 관한 모든 질문에 답변할 수 있으며 다른 주제나 일반적인 대화도 가능합니다.
                             제공된 컨텍스트에 필요한 정보가 없으며 잘 모르는 경우 '모르겠습니다'라고 응답해 주세요.
                             당신은 AWS EC2를 생성하기도 하고, 리부팅하기도 하며, ec2를 관리하는데 필요한 업무를 수행할수 있습니다.  
                             질문이나 요청을 받았을 때 키워드,예약어를 비롯하여 AWS CLI를 포함한 명령어를 제외하고는 한글로 설명해주세요.
    
    <question>
    {user_request}
    </question>
    Assistant:"""

    claude_input = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": prompt_data}]}
            ],
            "temperature": 0.5,
            "top_k": 250,
            "top_p": 1,
            "stop_sequences": [],
        }
    )

    response = client.invoke_model(modelId=model_Id, body=claude_input)
    response_body = json.loads(response.get("body").read())
    print("------prompt:", prompt_data)

    try:
        message = response_body.get("content", [])
        result = message[0]["text"]
    except (KeyError, IndexError):
        result = "잘 모르겠습니다. 제가 할수 없거나 모르는 내용입니다."

    print("interact_with_general llm result:", result)
    return result


def chat_with_claude(user_message, tool_config):
    client = boto3.client("bedrock-runtime")
    model_Id = "anthropic.claude-3-sonnet-20240229-v1:0"

    messages = [{"role": "user", "content": [{"text": user_message}]}]

    tool_functions = {
        "get_cpu_info": get_cpu_info,
        "launch_ec2": launch_ec2,
        "terminate_ec2": terminate_ec2
    }

    def call_tool(tool, messages):
        tool_name = tool["name"]
        tool_input = tool["input"]
        
        if tool_name == "get_price":
            result = tool_functions[tool_name](tool_input["fruit"])
        elif tool_name in ["get_cpu_info","launch_ec2","terminate_ec2"]:
            result = tool_functions[tool_name]()
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        content = {"result": result}
        tool_result = {
            "toolUseId": tool["toolUseId"],
            "content": [{"json": content}],
        }
        tool_result_message = {
            "role": "user",
            "content": [{"toolResult": tool_result}],
        }
        
        messages.append(tool_result_message)
        
        print(messages)
        
        response = client.converse(
            modelId=model_Id, messages=messages, toolConfig=tool_config
        )
        return response["output"]["message"]
  
    response = client.converse(
        modelId=model_Id, messages=messages, toolConfig=tool_config
    )

    output_message = response["output"]["message"]
    messages.append(output_message)
    stop_reason = response["stopReason"]
    
    if stop_reason == "tool_use":
        tool_requests = output_message["content"]
        for tool_request in tool_requests:
            if "toolUse" in tool_request:
                output_message = call_tool(tool_request["toolUse"], messages)
        return output_message["content"][0]["text"]
    else:
        # Handle general questions without tool use
        claude_input = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": user_message}]}
                ],
                "temperature": 0.5,
                "top_k": 250,
                "top_p": 1,
                "stop_sequences": [],
            }
        )

        response = client.invoke_model(modelId=model_Id, body=claude_input)
        response_body = json.loads(response.get("body").read())

        try:
            message = response_body.get("content", [])
            result = message[0]["text"]
        except (KeyError, IndexError):
            result = "I'm sorry, I couldn't generate a response."
        
        st.write(result)
        return result

tool_config = {
    "tools": [
         {
            "toolSpec": {
                "name": "get_cpu_info",
                "description": "선택된 ec2(인스턴스)의 CPU 정보를 조회하고 그래프를 그려달라고 할때 이 함수를 사용, 예를 들어 각 ec2의 CPU정보 알려줘 할때 수행됨 ",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "ec2",
                            }
                        },
                        "required": [],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "launch_ec2",
                "description": "선택된 ec2를 복제합니다. 인스턴스를 생성해주세요 또는 추가해주세요.  ec2를 생성해주세요. ec2를 복제해주세요 로 이 함수를 실행합니다.  ",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "ec2",
                            }
                        },
                        "required": [],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "terminate_ec2",
                "description": "선택된 ec2를 삭제합니다. ec2를 삭제해주세요. 인스턴스를 삭제해주세요. ec2를 제거해주세요 할때 이 함수를 실행합니다.  ",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "ec2",
                            }
                        },
                        "required": [],
                    }
                },
            }
        },
    ]
}

def main():
    
    # 채팅 입력
    prompt = st.chat_input("ec2 관리를 위한 명령을 내리거나 cpu정보를 조회 하세요.")
    
    if prompt is not None:
        print("prompt:-----", prompt)
            
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        chat_with_claude(prompt, tool_config)

if __name__ == "__main__":
    main()