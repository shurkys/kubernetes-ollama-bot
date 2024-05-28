import logging
import time

import cachetools
import ollama
from robusta.api import *

# Define cache size and LRU cache
cache_size = 100
lru_cache = cachetools.LRUCache(maxsize=cache_size)
class OllamaServerParams(ActionParams):
    """
    :var model: Ollama model
    :var host: URL for the Ollama host
    """
    model: str = "llama3"  # Default model for Ollama
    host: str = "http://localhost:11434"  # Default host for Ollama

class OllamaParams(OllamaServerParams):
    """
    :var search_term: Ollama search term
    """
    search_term: str


@action
def show_ollama_search(event: ExecutionBaseEvent, params: OllamaParams):
    """
    Add a finding with Ollama top results for the specified search term.
    This action can be used together with the stack_overflow_enricher.
    """
    client = ollama.Client(host=params.host)

    logging.info(f"Ollama search term: {params.search_term}")

    answers = []
    try:
        if params.search_term in lru_cache:
            answers = lru_cache[params.search_term]
        else:
            start_time = time.time()
            messages = [
                {"role": "system", "content": "You are a helpful assistant that helps Software Developers and DevOps Engineers to solve issues relating to Prometheus alerts for Kubernetes clusters. You are factual, clear and concise. Your responses are formatted using Slack specific markdown to ensure compatibility with displaying your response in a Slack message."},
                {"role": "user", "content": f"Here are the rules for Slack specific markdown, make sure to only use the following syntax in your responses: Text formatted in bold Surround text with asterisks: '*your text*', '**' is invalid syntax so do not use it. Text formatted in italics, surround text with underscores: '_your text_'. Text formatted in strikethrough, surround text with tildes: '~your text~'. Text formatted in code, surround text with backticks: '`your text`'. Text formatted in blockquote, add an angled bracket in front of text: '>your text'. Text formatted in code block, add three backticks in front of text: '```your text'. Text formatted in an ordered list, add 1 and a full stop '1.' in front of text. Text formatted in a bulleted list, add an asterisk in front of text: '* your text'."},
                {"role": "user", "content": f"When responding, use Slack specific markdown following the rules provided. Always bold and italic headings, i.e '*_The heading:_*', to clearly separate the content with headers. Don't include any conversational response before the facts."},
                {"role": "user", "content": f"Please describe what the Kubernetes Prometheus alert '{params.search_term}' means, giving succinct examples of common causes. Provide any possible solutions including any troubleshooting steps that can be performed. Give a real-world example of a situation that can cause the alert. Clearly separate sections for Alert Name, Description, Real World Example, Common Causes, Troubleshooting Steps, and Possible Solutions."},
            ]

            logging.info(f"Ollama input: {messages}")
            res = client.chat(
                model=params.model,
                messages=messages,
            )
            if res:
                logging.info(f"Ollama response: {res}")
                response_content = res['message']['content']
                total_tokens = res.get('usage', {}).get('total_tokens', 0)
                time_taken = time.time() - start_time
                lru_cache[params.search_term] = [response_content]  # Store only the main response in the cache
                answers.append(response_content)

            answers.append("\n\n ---")
            answers.append(f"\n\n | Time taken: {time_taken:.2f} seconds | Total tokens used: {total_tokens} |")

    except Exception as e:
        logging.error(f"Error calling Ollama client: {e}")
        answers.append(f"Error calling Ollama client: {e}")
        raise

    finding = Finding(
        title=f"Ollama ({params.model}) Results",
        source=FindingSource.PROMETHEUS,
        aggregation_key="Ollama Wisdom",
    )

    if answers:
        finding.add_enrichment([MarkdownBlock('\n'.join(answers))])
    else:
        finding.add_enrichment(
            [
                MarkdownBlock(
                    f'Sorry, Ollama doesn\'t know anything about "{params.search_term}"'
                )
            ]
        )

    event.add_finding(finding)
    logging.info("Finding added to event")

@action
def ollama_enricher(alert: PrometheusKubernetesAlert, params: OllamaServerParams):
    """
    Add a button to the alert - clicking it will ask Ollama to help find a solution.
    """
    alert_name = alert.alert.labels.get("alertname", "")
    if not alert_name:
        return

    alert.add_enrichment(
        [
            CallbackBlock(
                {
                    f'Ask Ollama: {alert_name}': CallbackChoice(
                        action=show_ollama_search,
                        action_params=OllamaParams(
                            search_term=alert_name,
                            model=params.model,
                            host=params.host,
                        ),
                    )
                },
            )
        ]
    )
