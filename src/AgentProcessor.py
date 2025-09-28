import gradio as gr
import time
import asyncio
import pandas as pd
from microsoft_agents.activity import ActivityTypes, load_configuration_from_env
from microsoft_agents.copilotstudio.client import (
    ConnectionSettings,
    CopilotClient,
)
resultsdf = pd.DataFrame(columns=['Serial', 'Query', 'Response', 'Time', 'ConversationId', 'CharLen'])
resultsaidf = pd.DataFrame(columns=['Serial', 'Query', 'PlannerStep', 'Thought', 'Tool', 'Tool Type', 'Arguments'])
import sys

class AgentProcessor:
    def __init__(self, name, connection):
        self.name = name
        self.connection = connection

    @property
    def data(self):
        print("Getting data...")
        return self._value

    def merge_dataframes(self, data):   
        # Merge the two DataFrames on the 'Serial' column
        aggregated_df = data.groupby('Query', as_index=False).agg(
            Steps=('Serial', 'count'),
            Planner=('PlannerStep', '>>'.join),
            Thought=('Thought', ''.join),
            Tool=('Tool', lambda x: ', '.join(x.unique())),
            Tool_Type=('Tool Type', ''.join),
            Arguments=('Arguments', ''.join)
        )
        return data
        #return aggregated_df

    def extract_and_format_json_data(self,list_of_dicts, keys_to_extract, separator=", "):
        if not isinstance(list_of_dicts, list) or not list_of_dicts:
            return ""
        formatted_items = []
        for item in list_of_dicts:
            # Build the list of key-value pair strings for the current dictionary
            key_value_pairs = [
                f"{key}: {item.get(key, 'N/A')}" for key in keys_to_extract
            ]
            # Join the key-value pairs for the current dictionary
            formatted_items.append(separator.join(key_value_pairs))

        # Join the formatted strings for all dictionaries
        return " \n ".join(formatted_items)
            
    def json_concat_simple(self, jsoncat):
        result = ""
        for item in jsoncat:
            result += str(item) + "\n"
        return result
    
    async def ask_question_file(self):
        try:
            act = self.connection.start_conversation(True)
            print("\nSuggested Actions: ")
            async for action in act:
                if action.text:
                    print(action.text)
            with (open('./data/input.txt', 'r', encoding='utf-8') as file):
                for line in file:
                    linecount = sum(1 for _ in file)
                print(f"\nTotal lines in file: {linecount}\n")
                # Iterate through each line in the file
            with (open('./data/input.txt', 'r', encoding='utf-8') as file):
                for line in file:
                    # Process each line (e.g., print it, manipulate it)
                    query = line.strip() # .strip() removes leading/trailing whitespace, including the newline character
                    print(f" - {query}")
                    if query in ["exit", "quit"]:
                        timestamp_str = time.strftime("%Y-%m-%d_%H-%M-%S")
                        # Construct the filename with a desired extension
                        filename = f"{action.conversation.id}_{timestamp_str}.csv"
                        # index=False prevents writing the DataFrame index as a column in the CSV
                        resultsdf.to_csv(f"./data/{filename}", index=False)
                        print(f"CSV file '{filename}' created successfully.")
                        print("Exiting...")
                        sys.exit(0)
                        
                    if query:
                        start_time = time.perf_counter()
                        replies = self.connection.ask_question(query, action.conversation.id)
                        async for reply in replies:
                            if reply.type == ActivityTypes.event:  
                                print(f" - {reply}")
                                # ['Serial', 'Query', 'PlannerStep', 'Thought', 'Tool', 'Tool Type', 'Arguments', 'Response']
                                if reply.value_type == "DynamicPlanReceived":
                                    resultsaidf.loc[len(resultsaidf)] = [len(resultsaidf) + 1, 
                                                                         query, 
                                                                         reply.value_type, 
                                                                         self.extract_and_format_json_data(reply.value['toolDefinitions'], ['displayName', 'description']),
                                                                         '', 
                                                                         self.extract_and_format_json_data(reply.value['toolDefinitions'], ['schemaName']),
                                                                         '']
                                if reply.value_type == "DynamicPlanStepTriggered":
                                    resultsaidf.loc[len(resultsaidf)] = [len(resultsaidf) + 1, 
                                                                         query, 
                                                                         reply.value_type, 
                                                                         reply.value['thought'], 
                                                                         reply.value['taskDialogId'], 
                                                                         reply.value['type'],
                                                                         '']
                                elif reply.value_type == "DynamicPlanStepBindUpdate":
                                    resultsaidf.loc[len(resultsaidf)] = [len(resultsaidf) + 1, 
                                                                         query, 
                                                                         reply.value_type, 
                                                                         '', 
                                                                         reply.value['taskDialogId'], 
                                                                         '', 
                                                                         str(reply.value['arguments'])]
                                elif reply.value_type == "DynamicPlanStepFinished":
                                    resultsaidf.loc[len(resultsaidf)] = [len(resultsaidf) + 1, 
                                                                         query, 
                                                                         reply.value_type, 
                                                                         '', 
                                                                         reply.value['taskDialogId'], 
                                                                         '', 
                                                                         '']    
                            if reply.type == ActivityTypes.message:
                                print(f"\n{reply.text}")
                                if reply.suggested_actions:
                                    for action in reply.suggested_actions.actions:
                                        print(f" - {action.title}")
                            elif reply.type == ActivityTypes.end_of_conversation:
                                print("\nEnd of conversation.")
                                sys.exit(0)
                        end_time = time.perf_counter()
                        elapsed_time = end_time - start_time
                        print(f"Total time taken for both steps: {elapsed_time:.6f} seconds")
                        resultsdf.loc[len(resultsdf)] = [len(resultsdf) + 1, query, reply.text, elapsed_time, action.conversation.id, len(reply.text)]
                        yield (
                            gr.update(interactive=False),
                            "Processing " + str(len(resultsdf)) + " of " + str(linecount) + " records.",
                            resultsdf['Time'].mean(),
                            resultsdf['Time'].median(),
                            resultsdf['Time'].max(),
                            resultsdf['Time'].min(),
                            resultsdf['Time'].std(),
                            resultsdf.sort_index(),
                            resultsdf.sort_index(),
                            self.merge_dataframes(resultsaidf.sort_index()),
                            resultsdf['CharLen'].corr(resultsdf['Time'])
                        )
            yield (
                gr.update(interactive=True),
                "Processing " + str(linecount) + " of " + str(len(resultsdf)) + " records.",
                resultsdf['Time'].mean(),
                resultsdf['Time'].median(),
                resultsdf['Time'].max(),
                resultsdf['Time'].min(),
                resultsdf['Time'].std(),
                resultsdf.sort_index(),
                resultsdf.sort_index(),
                self.merge_dataframes(resultsaidf.sort_index()),
                resultsdf['CharLen'].corr(resultsdf['Time'])
            )
        except Exception as e:
            print(f"Error: {e}")
            yield (
                gr.update(interactive=True),
                f"Error: {e}",
                resultsdf['Time'].mean() if not resultsdf.empty else 0,
                resultsdf['Time'].median() if not resultsdf.empty else 0,
                resultsdf['Time'].max() if not resultsdf.empty else 0,
                resultsdf['Time'].min() if not resultsdf.empty else 0,
                resultsdf['Time'].std() if not resultsdf.empty else 0,
                resultsdf.sort_index() if not resultsdf.empty else pd.DataFrame(),
                resultsdf.sort_index() if not resultsdf.empty else pd.DataFrame(),
                self.merge_dataframes(resultsaidf.sort_index()) if not resultsaidf.empty else pd.DataFrame(),
                resultsdf['CharLen'].corr(resultsdf['Time']) if len(resultsdf) > 1 else 0
            )