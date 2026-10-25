# AI Prompts Log — Final Project

My actual prompts to the AI coding assistant (Claude Code), recorded verbatim in order.

---

## Prompt 1

> Now, I'm starting Final Project in final project in AI code.

## Prompt 2

> In this project. I wanna build an AI agent web app for helping municipal emergency staff coordinate food distribution to evacuation shelters after a disaster, like big earthquake.
> The app should take shelter reports and municipal warehouse inventory (CSV), figure out how much food each shelter needs, and suggest a proportional allocation based on unmet demand. If there's not enough food, it should show the shortage and help draft a request for additional supplies from the prefectural or national government.
> Shelter populations change, so the app should use the latest validated data when staff finalize the day's allocation and replenishment request. I also wanna explore using AI Vision to compare warehouse photos with the inventory CSV.
> Don't hardcode shelter counts, population numbers, or inventory quantities. We'll use sample data later for testing.
> Now, create AI_prompts.md to record my actual prompts, and suggest a simple architecture and development plan. Also, create a concise project_spec.md covering the app's purpose, core workflow, and the decisions we've made so far. Leave unresolved design details open for discussion. Set up a minimal project structure, .gitignore, and .env.example with PORTKEY_API_KEY as a placeholder. Never store a real API key in the repo.

## Prompt 3

> Use gpt-6-luna through Portkey with PORTKEY_API_KEY, not gpt-5.6-luna.
> AI agent should also read unstructured shelter reports and extract useful information, such as evacuee counts, available food, special requirements, and report timestamps. Staff should review and validate these extracted values before they're used.
> Define simple CSV formats for shelter data and municipal warehouse inventory. The number of shelters and all quantities should remain flexible. Use 3 meals per person per day and a 24-hour planning window as configurable defaults, not hardcoded assumptions.
> Propose the data fields and how updates will be recorded, especially how the app will use the latest validated data when staff finalize the allocation.
> Update project_spec.md and record this exact prompt in AI_prompts.md.

## Prompt 4

> Don't treat all food as interchangeable. Proportional allocation should apply only to compatible general meals. Keep special dietary requirements separate and flag shortages or missing information for staff review.
> Track approved and dispatched allocations so that previously dispatched food isn't counted as available warehouse inventory again.
> When staff finalize a plan, use the latest validated data and recalculate. If the result has changed, show the updated plan and require staff to confirm it before finalizing.
> Implement and test the data loading, validation, and allocation calculations first. Keep the number of shelters and all quantities flexible, and handle rounding deterministically.
> Use small test datasets only to verify the calculations, not as hardcoded app assumptions.
> Update project_spec.md if needed, and record this exact prompt in AI_prompts.md.

## Prompt 5

> Don't build the AI agents or web UI yet. Show me the test results and explain any remaining design decisions before moving on.

## Prompt 6

> I wanna create a simple Dash chat interface for “Disaster FoodBridge” , then build and connect the PydanticAI agent and its tools step by step.
> For now, just make a minimal app.py with a chat window, message input, conversation history, a loading indicator, and optional tool activity display.
> Have the UI call a run_agent() function, but don't implement the real agent yet. A tiny placeholder response is fine for now.
> Keep the UI simple. Don't redesign the whole app or touch the existing allocation and validation code.
> Run the Dash app locally and verify that the chat interface works.
> Record this exact prompt in AI_prompts.md, then show me the result before moving on.

## Prompt 7

> Replace the placeholder run_agent() with a real PydanticAI agent.
> Use gpt-6-luna through Portkey with PORTKEY_API_KEY, and pydantic-ai-slim[openai].
> The agent should act as a municipal emergency food distribution assistant and respond to basic questions through the existing Dash chat.
> Keep the current run_agent(message, history) interface and the UI unchanged. Include conversation history, a reasonable request limit, and basic error handling.
> Don't add tools, additional agents, or new features yet. Don't modify the existing allocation logic.
> Test one real model response through the chat interface. Show me the actual response, token usage, and any errors.
> Record this exact prompt in AI_prompts.md, then stop so we can review the result before moving on.

## Prompt 8

> Add the first tool to our PydanticAI agent: get_shelter_reports.
> Use the existing record-management code to retrieve the latest validated report for each shelter, including shelter ID, name, evacuee count, food on hand, and report timestamp.
> If there are newer reports pending validation, the agent should mention that. If no validated data is available, it should say so rather than invent numbers.
> Test the tool through the Dash chat with a question like "What's the latest situation at our evacuation shelters?"
> Show me the actual tool call, returned data, agent response, and token usage. If sample data is needed, keep it separate from the application logic.
> Record this exact prompt in AI_prompts.md and stop for review.

## Prompt 9

> Fix the chat so Markdown tables render properly. Keep the UI change minimal.
> Then add our second tool: get_warehouse_inventory.
> Use the existing inventory loading and validation code to retrieve available warehouse food inventory, including item name, quantity, meal equivalents, dietary category, and inventory timestamp.
> The agent should use this tool when asked about available food supplies. It must distinguish general meals from special-diet items and never invent stock quantities.
> Test it through the Dash chat with a question like "How much food do we currently have available?" Show the actual tool call, returned data, agent response, and token usage.
> Keep sample data separate from application logic. Don't implement allocation tools or any other features yet.
> Record this exact prompt in AI_prompts.md and stop for review.

## Prompt 10

> Currently, get_warehouse_inventory reports validated counted stock without subtracting previously dispatched food.
> Connect it to our existing dispatch-tracking logic so the agent can distinguish counted inventory from actually available inventory.
> Make sure we don't double-count dispatches, especially when newer warehouse recounts are recorded.
> Test a simple case where food is dispatched after the latest stock count, and another case where a newer recount replaces the earlier count.
> Show me the actual numbers before and after, the tool response, and the test results.
> Record this exact prompt in AI_prompts.md and stop for review.

## Prompt 11

> Yes, ask the agent how much food is available through the chat and show me the response and token usage.

## Prompt 12

> Add a PydanticAI tool called calculate_shelter_needs that uses our existing Python calculation logic and the latest validated shelter reports.
> For each shelter, calculate the food required for the planning period, subtract food already on hand or on its way, and show the remaining unmet demand.
> Use our configurable meal rate and planning window. Keep general meals separate from special dietary needs, and flag missing or uncertain information rather than guessing.
> Test it through the Dash chat with a question like "How much food does each shelter still need for the next 24 hours?"
> Show the actual tool call, calculation results, agent response, and token usage.
> Record this exact prompt in AI_prompts.md and stop for review.

## Prompt 13

> We shouldn't assume that food has been delivered just because it was dispatched before the shelter's latest report. In a disaster, deliveries can be delayed.
> Distinguish clearly approved, dispatched, delivered, and cancelled food.
> Approved food should be shown as committed but not yet shipped. Dispatched food should be shown as shipped but not confirmed delivered. Only confirmed deliveries should be marked as delivered.
> Make sure these states are reflected consistently in the needs calculation, without double-counting food or automatically assuming delivery.
> Keep the changes focused on this issue. Add tests for delayed deliveries and newer shelter reports.
> Record this exact prompt in AI_prompts.md and stop for review.

## Prompt 14

> Verify the updated delivery states through the Dash chat before moving on.
> Ask the agent about each shelter's remaining food needs and the status of food already committed or shipped.
> Check that it clearly distinguishes approved but not shipped, dispatched but not confirmed delivered, and confirmed delivered food.
> Show me the actual agent response, tool calls, token usage, and any warnings. 
> Record this exact prompt in AI_prompts.md and stop for review.

## Prompt 15

> Approved, dispatched, and confirmed-delivered food should remain separate. A confirmed delivery made after the latest shelter report should count toward reducing unmet demand, but it shouldn't be described as still on its way.
> Update the tool's output labels and the agent's wording to reflect these distinctions accurately. Keep the underlying calculation and existing UI unchanged.
> Run the relevant tests and show me the before-and-after output.

## Prompt 16

> Add the next PydanticAI tool: calculate_allocation.
> Use our existing Python allocation logic and the latest validated shelter reports and available warehouse inventory. Don't rewrite the calculation logic.
> I want two plans:
> Plan A: a proportional allocation that is feasible with the currently available stock.
> Plan B: the full allocation needed to meet all validated unmet demand if additional food is procured.
> Show the allocation for each shelter, the total shortage, and any special-diet needs or unresolved data warnings. Keep general meals separate from special diets.
> The agent should use this tool when asked to prepare a food distribution plan. Make clear that it's a draft, not a finalized allocation.
> Test it through the Dash chat with "Prepare a food allocation plan for our evacuation shelters."
> Show me the actual tool calls, allocation figures, agent response, token usage, and test results.

## Prompt 17

> Add the next capability: drafting a food supply request to the prefectural or national government.
> When staff ask for a supply request, the agent should use the results from calculate_allocation to draft a clear, professional request.
> Include the planning period, general-meal shortage, additional supplies needed, special-diet requirements, and any pending or uncertain data. Use placeholders for unknown municipality names, recipients, and delivery details instead of inventing them.
> Clearly label the request as a DRAFT requiring staff review. Don't send anything or finalize any allocation.
> Test it through the Dash chat with "Draft a request for additional food supplies based on our current allocation plan."
> Show me the actual tool calls, draft, token usage, and any errors.

## Prompt 18

> Review the finalization and record-management logic we've already built.
> I wanna understand how the system checks the latest validated shelter reports, warehouse inventory, and dispatch records when staff are ready to finalize an allocation plan and its associated supply request.
> Check whether a change in any relevant data would trigger recalculation and staff reapproval. Also check how the plan and supply request are linked.
> Show me what already works, what is missing, and any risks you find. Run relevant existing tests, but don't implement or change anything yet.

## Prompt 19

> Focus only on safely persisting finalized allocation plans and preventing two staff members from finalizing the same reviewed plan simultaneously.
> I SQLite transactions might be appropriate here, while keeping our existing CSV-based data loading. Evaluate that approach briefly and implement the smallest reliable solution.
> Reuse the existing finalize_plan() calculations and checks. A successful finalization should persist the plan snapshot and its approved allocation records atomically, and a second attempt using the same reviewed plan should fail safely without duplicating commitments.
> Test successful finalization, a repeated finalization attempt, and two simultaneous finalization attempts. Show me the stored results and test outcomes.

## Prompt 20

> The system should check for newer shelter reports or warehouse counts that are still pending validation, and shelters with no validated reports.
> If any exist, finalization should stop and return clear warnings. Staff should be able to proceed only after explicitly acknowledging the specific warnings and recording a reason for proceeding without those data.
> If the pending data or warnings change before finalization, require a fresh review and acknowledgement.
> Store the acknowledgements and reasons with the finalized plan for audit purposes.
> Implement this in the existing finalization logic and test normal finalization, missing acknowledgements, acknowledged warnings, and warnings that change before finalization.

## Prompt 21

> Make the existing finalization workflow accessible to staff through the Dash app.
> Add a minimal allocation review and finalization section to the existing UI.
> Staff should be able to review the current Plan A, see the data warnings, acknowledge each warning with a reason, and explicitly confirm finalization.
> Use the existing SQLite finalization logic. Recheck the latest validated data when Finalize is clicked. If the plan or warnings have changed, show the updated plan and require a fresh review instead of finalizing automatically.
> Show the saved Plan ID after successful finalization. The AI agent must not be able to finalize a plan through chat or a tool.
> Keep the existing chat working. Don't add supply-request saving, new agents, or other features yet.
> Test the complete flow in the browser, including a successful finalization and a case where the data changes before confirmation. Show me the results and test outcomes.

## Prompt 22

> Link each finalized allocation plan to its corresponding draft supply request.
> The supply request should use the same validated data and allocation results as the finalized plan, including the planning period, shortages, special dietary requirements, and warnings.
> Save the draft request in SQLite with the finalized Plan ID and fingerprint, so staff can retrieve the exact request associated with that plan later.
> Make sure the request is not silently regenerated from newer data after finalization. It should remain an auditable snapshot of what was known when the plan was finalized.
> Keep the request labeled as a draft requiring staff review. Don't send anything externally.
> Test that the saved request matches its finalized plan, and that later changes to shelter reports or inventory don't alter the stored request.
> Also, use UTC for stored timestamps and a configurable local timezone for display, defaulting to Asia/Tokyo for our sample scenario.

## Prompt 23

> Before continue implementing new features, I wanna organize our development history for the final project report.
> Create development_log.md summarizing our actual development process so far, using AI_prompts.md, the current code, and test results.
> For each major stage, record:
> -Objective and relevant prompt numbers
> -What we implemented and why
> -Important design decisions
> -Bugs we discovered and how we fixed them
> -Actual tests and results
> -Remaining limitations
> Also create evidence_index.md linking important claims to available tests, code, logs, and screenshots. Clearly mark evidence that we still need to collect.
> Keep this factual. Don't invent past decisions, measurements, user feedback, or test results. Distinguish what was actually tested from what was only implemented or proposed.
> Don't rewrite AI_prompts.md, and don't modify any application code.
> We'll use these files later to write the final report, so keep them organized and easy to update.
> Record this exact prompt in AI_prompts.md and stop for review.

## Prompt 24

> Preserve the screenshots as evidence.
> Copy the 14 existing screenshots into evidence/screenshots/ within the project. Don't modify the originals.
> Give each screenshot a clear filename and update evidence_index.md with its location, what it demonstrates, and the relevant development stage.
> Please distinguish screenshots showing successful behavior from those showing bugs or intermediate results. Don't claim a screenshot proves something it doesn't actually show.

## Prompt 25

> Continue with the next AI capability: extracting structured information from free-text shelter reports.
> Use PydanticAI with gpt-6-luna to extract shelter ID or name, evacuee count, available food, special dietary requirements, and report timestamp from natural-language reports.
> Use a Pydantic output model. Preserve the original report text, leave missing values unknown, and flag ambiguous or conflicting information rather than guessing.
> For now, test the extraction on a few realistic examples, including incomplete and contradictory reports. Show me the original text, structured output, warnings, and actual token usage.
> Don't save these reports as validated data or change the allocation and finalization logic yet. We'll add staff review in the next step.
> Record this exact prompt in AI_prompts.md, update development_log.md and evidence_index.md with verified results, and stop for review.

## Prompt 26

> Add staff review and validation as the next step.
> Create a simple section in the existing Dash app where staff can paste a free-text shelter report, run the extraction, and review the structured fields alongside the original text and any warnings.
> Staff should be able to correct missing or incorrect fields before explicitly approving the report.
> Only after staff approval should the corrected record be added to our existing shelter report log as validated data. Keep the original text and a record of who approved it and when. Never overwrite earlier reports.
> Make sure the new validated report is picked up when the allocation plan is recalculated, and that a previously reviewed plan requires fresh confirmation if the data changed.
> Test the workflow in the browser, including an incomplete report, a corrected field, and the effect on allocation.

## Prompt 27

> Fix the data storage issue before moving on.
> The app currently reads sample CSV files directly, so approving a report could modify our original sample data.
> I want data/sample/ to remain unchanged. Make the app use working copies under data/live/ for normal operation, including shelter reports, inventory, and dispatch records.
> On first setup, it can copy the sample data into the working directory, but it must not overwrite existing working data on restart.
> Make sure finalization and allocation use the same working dataset, and keep the working files excluded from git.
> Test report approval, allocation recalculation, finalization, and app restart. Verify that the original sample files remain byte-for-byte unchanged.

## Prompt 28

> Add the warehouse photo analysis capability to Disaster FoodBridge.
> Create a PydanticAI vision tool called analyze_warehouse_photo using gpt-6-luna through Portkey.
> It should analyze an uploaded warehouse photo and identify visible food items, readable labels, and estimated quantities, using structured output. Clearly distinguish observed facts from uncertain estimates.
> Compare the observations with the relevant validated inventory CSV records and flag possible discrepancies for staff review. A photo may show only part of the warehouse, so never assume it represents total stock.
> Keep the image associated with its analysis so staff can inspect it and ask follow-up questions later.
> For now, implement the vision logic separately and test it with one or two sample photos. Show the actual images, model output, comparison results, token usage, and limitations.
> Don't change the inventory records or allocation logic, and don't build a new desktop/browser interface.

## Prompt 29

> Add a simple warehouse photo analysis section to our existing Dash app.
> Staff should be able to upload a photo, select the warehouse, run the existing vision analysis, and review the identified items, estimated quantities, uncertainties, and possible discrepancies against validated inventory.
> Show the uploaded image alongside the analysis, and let staff ask follow-up questions about that same image using our existing ask_about_photo() function.
> Keep this read-only. No image analysis should automatically change inventory records or allocation plans.
> Test the workflow in the browser with the two synthetic images, including a follow-up question. Show the actual results, token usage, and any errors.

## Prompt 30

> Begin the safety evaluation with a realistic prompt-injection attack against the shelter report extraction workflow.
> First, run a normal shelter report as the baseline. Then create a modified version containing the same factual information plus malicious instructions embedded in the report text, such as telling the AI to skip validation, mark the report as approved, or suppress warnings.
> Run both through the actual PydanticAI extraction agent and compare the structured outputs, warnings, and validation results.
> Record the exact inputs, outputs, token usage, and whether the attack affected the result. Check whether any untrusted instructions were followed.
> Don't change the defenses yet. I want to see the baseline and attack results first, then decide what to fix.
> Use only isolated test data. Don't modify live records or finalized plans.
> Save the evidence under evidence/safety/, update development_log.md and evidence_index.md, and record this exact prompt in AI_prompts.md.

## Prompt 31

> Improve the shelter report extraction workflow by detecting suspicious instructions embedded in untrusted report text.
> I want the system to flag attempts to override the AI's behavior, suppress warnings, manipulate extracted values, or bypass staff approval. Keep the original report and show the warning to staff.
> Don't rely only on exact keyword matching, and avoid flagging ordinary operational instructions meant for human emergency staff.
> Keep the existing extraction, validation, and human-approval rules unchanged.
> First test the defense against the exact baseline and two attacks saved from P30. Then test a few benign reports to check for false positives.
> Show the before-and-after results, detection outcomes, any false positives, and actual token usage. Don't claim the attacks were successful when they weren't.
> Save the evidence under evidence/safety/, update development_log.md and evidence_index.md, and record this exact prompt in AI_prompts.md.
> Stop for review before implementing any other safety features.

## Prompt 32

> Analyze tokenomics for Disaster FoodBridge.
> First, inventory the actual model usage records and identify which token fields are measured, missing, or uncertain.
> Verify the current official pricing for gpt-6-luna, including the conditions for cached input and cache writes. Record the source URL and date checked. Don't assume our course's Portkey account is billed at those rates.
> Build a small pricing calculation that clearly separates measured token usage, published API rates, estimated cost, and assumptions.
> Summarize the estimated cost of each major workflow: chat/tool calling, shelter report extraction, safety screening, and warehouse photo analysis.
> Identify what additional measurements are needed before we can estimate per-user costs and scale to 100 or 10,000 users.
> Don't add UI cost meters, budget controls, or caching optimizations yet. Don't change existing agent behavior.
> Save the analysis and supporting calculations under evidence/tokenomics/, add tests, update development_log.md and evidence_index.md, and record this exact prompt in AI_prompts.md.

## Prompt 33

> Yes, but first add a shared usage logger for our existing model calls: chat agent, report extraction, safety screening, warehouse photo analysis, and photo follow-up questions.
> Record each actual API call separately, including its workflow, model, timestamp, input tokens, output tokens, cached-read tokens, cache-write tokens, reasoning tokens, and any other usage details the API provides.
> Preserve missing fields as unknown, not zero. Keep measured usage separate from estimated USD costs, and don't treat Portkey caching or billing as verified unless the API reports it.
> Make the logs append-only and avoid recording API keys, sensitive report text, or full image contents. Don't double-count individual model calls.
> Test one real call from each workflow where practical, inspect the actual returned usage fields, and show which fields are available versus missing.
> Don't change existing agent behavior or add other features yet. Record this prompt in AI_prompts.md, update development_log.md and evidence_index.md with verified results, and stop for review.

## Prompt 34

> Yes, recompute our tokenomics using the new data/live/usage_log.jsonl.
> Use the actual per-call records to calculate estimated costs by workflow, including input, cached-read, cache-write, and output tokens.
> Distinguish OpenAI/Azure prompt caching from Portkey response-cache HITs. A Portkey HIT may replay the original usage numbers, so don't automatically treat those tokens as newly billed usage.
> Where cache-write duration or Portkey billing is unknown, show clearly labeled cost scenarios rather than claiming an exact charge.
> Compare the updated cost estimates with the previous estimates saved under evidence/tokenomics/, and explain what changed and why.
> Also identify one practical cost optimization worth testing next, considering both savings and possible effects on quality or safety.
> Don't change model behavior, prompts, caching settings, or the UI yet.
> Save the calculations and assumptions under evidence/tokenomics/, add tests, update development_log.md and evidence_index.md, record this exact prompt in AI_prompts.md, and stop for review.

## Prompt 35

> Test the proposed prompt-cache optimization for warehouse photo follow-up questions.
> First, establish a baseline using the current implementation. Then make the smallest change needed to improve reuse of the stable image and analysis context across follow-up questions about the same photo.
> Use the same test image and questions before and after the change. Compare actual cached-read and cache-write tokens, estimated costs, and answer quality.
> Make sure the test distinguishes provider calls from Portkey response-cache HITs. Don't claim savings based on replayed usage data.
> Verify that answers remain accurate, uncertainty is preserved, and instructions embedded in an image are treated as untrusted content. Also check that a different photo cannot reuse the wrong context.
> Keep the existing inventory and allocation logic unchanged. Don't add new UI features.
> Save the baseline and optimized results under evidence/tokenomics/, including actual usage logs and any failures. Update the relevant tests, development_log.md, and evidence_index.md, and record this exact prompt in AI_prompts.md.

## Prompt 36

> I want to try Disaster FoodBridge myself as an end user.
> Launch the current app at http://localhost:8050 and make sure it's ready for manual testing.
> Give me a brief walkthrough of the main workflows: chat, shelter report intake, allocation review and finalization, and warehouse photo analysis.
> Explain which actions will modify working data, and how I can safely reset the demo afterward without changing the original sample files.
> Don't implement anything new or run the workflows on my behalf. I want to operate the app myself first.

## Prompt 37

> Improve the Disaster FoodBridge UI to make it more intuitive and visually appealing for municipal emergency staff.
> Focus on three improvements:
> 1.Add a dashboard with key summary cards: available meals, unmet demand, additional supplies needed, and pending or missing reports.
> 2.Display shelter information as visual cards with evacuees, food needs, available food, shortages, and clear warning indicators.
> 3.Make Plan A vs. Plan B easy to understand using simple charts, visual comparisons, and short explanations.
> Use clean layouts, intuitive icons, and consistent colors. Reduce dense text and tables where possible, while keeping detailed information accessible.
> Use the existing validated data and calculations. Don't hardcode figures or change business logic, safety rules, or approval workflows.
> Implement these three improvements first, test them in the browser, and stop for review before making other UI changes.
> Record this prompt in AI_prompts.md and update development_log.md and evidence_index.md with verified results.

## Prompt 38

> Redesign dashboard to make it much easier for emergency staff to understand and act on.
> The current screen has too many cards, numbers, warnings, and charts competing for attention. I want a cleaner, more intuitive operational dashboard.
> Organize the screen into three sections, in this order:
> 1.Current situatin
> -Show three prominent numbers: available general meals, total unmet demand, and additional meals needed.
> -Include a simple visual bar showing how much of the demand can be covered by current inventory.
> -Keep secondary information out of this section.
> 2.Actions required
> -Show a short, prioritized list of issues that staff need to resolve, such as pending shelter reports, missing validated reports, unknown special-diet counts, and pending inventory updates.
> -Each item should explain what is wrong, why it matters, and what staff should do next.
> -Provide navigation to the relevant tab where possible.
> -Derive everything from actual data and warnings, not hardcoded examples.
> 3.ALLOCATION PLAN
> -Show Plan A and Plan B side by side.
> -Clearly explain that Plan A uses available inventory, while Plan B requires additional procurement.
> -Use simple horizontal bars to show proposed allocations and remaining shortages by shelter.
> -Keep special diets separate from general meals.
> -Put detailed shelter information, assumptions, and timestamps in expandable sections.
> Design guidelines:
> -Use larger, readable text and generous spacing.
> -Use a restrained, consistent color scheme: neutral for normal information, amber for uncertainty, and red for shortages requiring attention.
> -Use simple icons only when they clarify meaning.
> -Avoid excessive cards, tiny labels, decorative charts, and repeated information.
> -Make the dashboard understandable within 10 seconds, without reading long explanations.
> -Never describe proposed allocations as already dispatched or approved.
> First give me a short layout plan, then implement the Dashboard changes and test them in the browser.

## Prompt 39

> I'd like to make the Disaster FoodBridge Dashboard more spatial and intuitive by adding an interactive map.
> First, check whether our existing shelter and warehouse records contain usable geographic coordinates. If they don't, create a small, clearly labeled set of fictional training coordinates for the sample shelters and warehouses. Never present those coordinates as real locations.
> Add a map to the Dashboard showing shelters and warehouses with distinct markers. Use marker colors or icons to indicate shortages, missing validated reports, or pending information.
> When staff select a shelter, show its current validated demand, proposed Plan A allocation, remaining shortage, and relevant warnings in a details panel beside the map.
> Keep the current high-level summary numbers and a compact actions-required list. Avoid adding more dense tables.
> Don't invent driving distances, delivery routes, or travel times. Don't change calculations, inventory records, allocation rules, or approval workflows.
> Use the existing Dash app and keep the implementation simple. Test the map interactions in the browser, save screenshots, record this exact prompt in AI_prompts.md, update development_log.md and evidence_index.md, and stop for review.

## Prompt 40

> I wanna measure how effectively Disaster FoodBridge supports emergency food allocation using our existing sample data.
> Start with three evaluations:
> 1.Accuracy: compare the application's calculated shelter needs, available inventory, Plan A allocations, and additional procurement requirements against independently calculated expected results.
> 2.Reliability: test how the application responds to missing shelter reports, pending updates, unknown special-diet counts, and changes to validated data.
> 3.Efficiency: measure the actual processing time for report extraction and allocation planning. Distinguish automated processing time from human review time, which we haven't measured.
> Run the evaluations using isolated data so existing records and finalized plans remain unchanged.
> Record the test cases, expected outcomes, actual outcomes, timing measurements, and any failures. Don't invent human productivity gains or claim real-world impact from synthetic data.
> Save the evidence under evidence/impact/, update development_log.md and evidence_index.md, and record this exact prompt in AI_prompts.md.
> Don't change application behavior or add new features. Stop for review after reporting the results.

## Prompt 41

> Yes, fix the two dashboard defects identified in the impact evaluation.
> F1: The Dashboard crashes with KeyError: 'other_note' when multiple warnings don't match an existing action category. Make sure all warnings can be displayed safely, including unexpected warning types.
> F2: A special-diet category with known unmet demand but zero available stock must be clearly labeled as a shortage, not "Enough in stock". Keep unknown demand distinct from confirmed zero demand.
> Reproduce the failing scenarios first, apply minimal fixes, and rerun the affected reliability tests. Confirm that the Dashboard renders correctly and that warning labels are accurate.
> Don't change allocation calculations, agent behavior, approval logic, or the overall UI layout.
> Save the before-and-after evidence under evidence/impact/, update the relevant tests, development_log.md, and evidence_index.md, and record this exact prompt in AI_prompts.md.

## Prompt 42

> Audit the repository for reproducibility and security.
> Check below
> -requirements.txt includes every dependency needed to run the app.
> -.env.example documents the required configuration without exposing secrets.
> -The API key can be loaded from the project directory or its parent.
> -A fresh installation initializes the working data safely from the sample files.
> -The README gives clear setup and launch instructions that a teaching assistant can follow in under 10 minutes.
> -API keys, personal data, runtime logs, and temporary files are excluded from git.
> -The existing tests and the main app still work.
> Then initialize git if needed and prepare the repository for GitHub. Check whether a GitHub remote already exists, but don't publish or push anything without telling me first.

## Prompt 43

> Review the 307 staged files and remove anything unnecessary for submission, such as temporary artifacts, duplicate evidence, local paths, or debugging files. Keep the source code, tests, README, sample data, and evidence needed for the final report.
> Confirm once more that no API keys, secrets, personal information, or live working data are included.
> Then create a private GitHub repository named disaster-foodbridge under my account (ajk723-yale), commit the project, and push the main branch.
> Add GitHub user zlisto as a collaborator with access to the private repository.
> Verify that the push succeeded, the repository is accessible, and the README is displayed correctly.
> Give me the repository URL and report any step that requires my manual action. Don't modify application behavior.

## Prompt 44

> Produce a polished, evidence-based report.html that is 10–15 pages when printed on US Letter paper.
> Write for an intelligent manager who has never seen the app. Explain the real-world problem, what we built, why the design matters, and what our tests demonstrate. Avoid unnecessary technical jargon and generic AI-generated prose.
> Follow these eight sections in this exact order:
> 1.Title + links
> Include the project name, my name, GitHub repository URL (https://github.com/ajk723-yale/disaster-foodbridge), and a one-sentence description. Don't claim the app is publicly deployed.
> 2.Motivation
> Explain the challenges of allocating emergency food across evacuation shelters when reports are incomplete, stock changes, and different dietary needs must be considered. Make the practical value clear without inventing statistics or interviews.
> 3.What is new here
> Compare Disaster FoodBridge honestly with named existing products and ChatGPT itself. Research and cite verifiable sources. Explain specifically what our app does differently, without claiming that existing products lack features unless verified.
> 4.The agents
> Explain the PydanticAI agent, its tools, the structured extraction and safety screening workflows, deterministic allocation calculations, photo analysis, and human approval. Include an architecture diagram and trace one actual agent run step by step using saved evidence and screenshots. Clearly distinguish AI decisions from deterministic calculations and staff actions.
> 5.Tokenomics
> Use the actual usage logs and experiments under evidence/tokenomics/. Show measured input, cached-read, cache-write, reasoning, and output tokens where available; estimated cost per workflow and per user per month; and scenarios for 100 and 10,000 users. Explain pricing assumptions, unknown Portkey billing, and the measured photo follow-up cache optimization, including its effect on answer quality. Never present estimated costs as actual bills.
> 6.Safety
> Describe the main risks and actual defenses: prompt injection, inaccurate extracted information, stale data, unauthorized finalization, and excessive model usage. Use our actual attack and defense experiments, including before/after detection results and screenshots. Distinguish safeguards we've implemented from limitations we haven't solved, particularly any absence of a hard token-spending cap.
> 7.Impact
> Use the measured allocation accuracy, reliability tests, extraction and planning times, and Dashboard defect discovery and fixes from evidence/impact/. Explain the sample size, methodology, and limitations. Do not invent real users, operational time savings, or field deployment results.
> 8.Limits + next steps
> Explain limitations including synthetic datasets and photos, missing or unvalidated information, unresolved inventory-recount assumptions, real-world operational validation, and future improvements.
> Design requirements:
> -One self-contained HTML file, with all screenshots, diagrams, CSS, and other assets embedded.
> -Professional editorial design with readable typography, clear charts, well-formatted tables, and carefully selected screenshots from the real app.
> -Use visual explanations where they improve understanding, not decorative filler.
> -Include source references and captions for important evidence.
> -Keep the writing substantive and concise; 10–15 pages of real content, not filler.
> Evidence and quality control:
> -Review the actual source code, saved reports, evidence_index.md, development_log.md, and relevant evidence folders before drafting.
> -Make every important numerical claim traceable to a test, log, screenshot, calculation, or clearly identified assumption.
> -Never invent experimental results, citations, app capabilities, or user feedback.
> -Identify unsupported claims or missing evidence explicitly for my review.
> -Verify that every screenshot and diagram is legible and correctly described.
> -Open the completed HTML, inspect its print layout, and confirm the actual US Letter page count is between 10 and 15, with no clipped content or awkward page breaks.
> -Check all eight required sections against the assignment rubric.
> Record this exact prompt in AI_prompts.md, update development_log.md and evidence_index.md with verified results, and stop for review.
> Tell me the report's location, verified printed page count, key evidence used, and any remaining weaknesses before we finalize it.

## Prompt 45

> Make three focused revisions.
> Motivation: I have professional experience supporting government coordination related to the Fukushima nuclear accident, but I have never managed food distribution. Explain how this experience informed my interest in decision-making with incomplete information, coordination across organizations, and human accountability. Present shelter food allocation as a new application of those lessons, not as something I personally managed. Don't invent specific experiences or incidents.
> Agent evidence: Ensure the step-by-step agent trace and screenshots are clearly identified as coming from the same execution. If they come from different runs, either collect consistent evidence from one run or label them separately.
> Impact: Preserve the measured results and clearly distinguish technical validation from real-world impact. No external municipal staff tested the app, and no human time savings were measured.
> Keep the rest of the report's structure and design. Verify the actual claims against saved evidence, preserve the 10–15-page printed length, and stop for review.

## Prompt 46

> Commit and push report.html and its supporting evidence and documentation to the existing GitHub repository.
> Verify that the push succeeds and the repository remains private with no secrets or live data included.
> Then stop. Don't start the slides or make further report changes yet.

## Prompt 47

> Create the final presentation for Disaster FoodBridge.
> Use the finalized report.html as the primary source of content and evidence. Create a professional, self-contained slides.html using reveal.js, with no more than 10 slides.
> Aim for 9 slides:
> 1.Title: project name, my name, and one-sentence pitch.
> 2.The problem: emergency food allocation with incomplete shelter reports and changing inventory.
> 3.Our solution: what Disaster FoodBridge does differently.
> 4.How it works: a clear visual diagram distinguishing AI agents, deterministic tools, and human approval.
> 5.Product demo: actual screenshots showing the Dashboard, allocation plans, and map.
> 6.Report intake and vision: how AI reads reports and warehouse photos while staff retain control.
> 7.Tokenomics: measured API usage, estimated costs, and the verified caching optimization.
> 8.Safety and impact: real attack-defense results, calculation accuracy, reliability, and processing times.
> 9.Limitations and next steps: what still needs to be tested before real-world deployment.
> Use real screenshots and verified figures from the report and evidence folders. Don't invent new claims or results.
> Design the slides for a short presentation:
> -Large, readable text and minimal prose.
> -Strong visual hierarchy, diagrams, charts, and screenshots.
> -Consistent styling inspired by the existing app, without excessive decoration.
> -Explain technical concepts in plain English for a nontechnical audience.
> Make slides.html self-contained, including images and all required reveal.js assets, so it works by double-clicking the file without an internet connection. Ensure arrow-key navigation and fullscreen mode work.
> Test the presentation in a browser, inspect every slide for clipping and readability, and verify the slide count is no more than 10.
> Tell me the slide count, file location, key evidence used, and any limitations.

## Prompt 48

> Commit and push slides.html and its supporting evidence and documentation to the existing GitHub repository.
> Before committing, run a final security check to ensure no API keys, secrets, personal information, or live working data are included.
> Verify that the GitHub push succeeds and the repository remains private. Don't modify the app, report, or slides.
