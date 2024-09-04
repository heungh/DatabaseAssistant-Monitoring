# Smart Database Assistant with GenAI:Claude3

# **Why this project is created**

This project began with the idea of applying LLM to manage a large number of Aurora MySQL databases, aiming to streamline database management.<br>
We introduced the concept of an Agent to the LLM, creating a simple demonstration that analyzes error logs, searches Cloudwatch metric information using natural language, and generates graphs.<br>
We hope this project will be of great help to customers who are considering implementing LLM to improve their database management efficiency.<br>

## **How to deploy and test the solution**

### 1. Upload damon.yaml in the CloudFormation console and create a stack.
- The da-mon.yaml file is available in this GitHub repository. 
- Download yaml file from home directory of da-mon repository 
- Upload da-mon.yaml on the Cloudformation and create a stack on us-east-1 


### 2. Once the stack creation is successful, directly connect to the created EC2 instance from the console and set up the environment and install libraries as follows:
```
    python3 -m venv myenv      
    source myenv/bin/activate  
    pip install --upgrade pip
    pip install mysql-connector-python
    pip install mysql.connector
    pip install boto3       
    pip install langchain-aws
    pip install gdown 
    export AWS_DEFAULT_REGION=us-east-1
```

### 3.Download data with command below:
```        
    gdown https://drive.google.com/drive/folders/15oie9_FlNv871sIIAFBPPM5h0J8s61TU?usp=sharing  --folder
```
- Then you can see da-mon folder and files below with command : ls -al /home/ec2-user
```
   - da-mon <folder>
     - setup.sh 
     - da-mon.py
     - load_data.py
     - data.json
```
        
- execute chmod on setup.sh and run setup.sh 
```
    chmod +x /home/ec2-user/da-mon/setup.sh
    /home/ec2-user/da-mon/setup.sh
```
- Now you can find da-mon.py copied on /home/ec2-user/

### 4. Edit da-mon.py and modify s3 bucket name variable in file

- Go to cloudformation console and find your stack you've made with da-mon.yaml <br>
- And go to resource or output tab and find s3 bucket name and copy it <br>
- open da-mon.py and find s3_bucket_name variable and copy name <br>
```
ex : s3_bucket_name = "test-s3bucket-fugwilwec8mx" 
```

### (optional) 4-1. Enable Performance insights and Enhanced monitoring on all Aurora mysql clusters.

- If Aurora mysql is not enabled with PI , <br>
  you have to modify PI on all instances of Aurora clusters. <br>

    
### 5. Running the application:

- execute “streamlit run da-mon.py” inside the EC2 instance to start the application. 

-    Then, proceed with the following questions in the chat window:
   ```
    a. can you select product table on gamedb1-cluster?
    b. can you join customer and order table on gamedb1-cluster?
    c. can you list top query on gamedb1-cluster?
    d. analyze query plan of this query on gamedb1-cluster
    e. can you compare schemas on clusters with gamedb prefix?
    f. execute sql on all clusters with gamedb prefix
    g. can you retrieve performance data on all clusters with gamedb prefix between 2024-07-22 00:00 and 2024-07-22 23:59:59?
   ```
-    For questions d and f, you need to attach analyze_query.sql and multiple_execution.sql files before proceeding.
-    After completing these tasks, please remove the attached files by clicking the X button.
-    For question g, you may not see results because pi metrics data are not stored right after creating Aurora mysql clusters. 
