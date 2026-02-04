"""
Principle-based tool description for vector_search
Focus on core purpose and decision-making principles
"""

VECTOR_SEARCH_TOOL_DESCRIPTION = """Search the Nutraley product catalog using semantic similarity.

PURPOSE:
Retrieve factual product information from the catalog to answer user questions accurately.

CORE PRINCIPLE:
When you need product facts (features, benefits, pricing, availability) that aren't already in the conversation, search for them. Never rely on general knowledge about Nutraley products.

DECISION RULE:
Ask yourself: "Do I need product-specific information from the catalog to answer this accurately?"
- YES → Use this tool
- NO → Respond directly using conversation context or general conversational ability

QUERY FORMULATION:
- Use natural language that captures user intent
- Include relevant context (category, benefit, use case)
- Broader queries work well for catalog browsing
- Specific queries work well for particular products

RESULT INTERPRETATION:
- Empty results mean the product/category doesn't exist in catalog
- Multiple results should be presented as options
- Similarity scores below threshold mean no good matches

The goal is accuracy, not speed. Search when uncertain."""
