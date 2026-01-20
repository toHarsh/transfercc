#!/usr/bin/env python3
"""Analyze ChatGPT export structure to understand how projects are stored"""

import json
import os

export_path = "/Users/harshkothari/Downloads/chatGPT Data"

# Load conversations
print("Loading conversations.json...")
with open(os.path.join(export_path, "conversations.json"), 'r') as f:
    conversations = json.load(f)

print(f"Total conversations: {len(conversations)}")

# Get all unique keys from conversations
all_keys = set()
for conv in conversations:
    all_keys.update(conv.keys())

print(f"\n=== All keys in conversations ===")
for key in sorted(all_keys):
    print(f"  - {key}")

# Sample first conversation (without mapping)
print(f"\n=== Sample conversation structure ===")
sample = {k: v for k, v in conversations[0].items() if k != 'mapping'}
for key, value in sample.items():
    if isinstance(value, str) and len(value) < 200:
        print(f"  {key}: {value}")
    elif isinstance(value, (int, float, bool, type(None))):
        print(f"  {key}: {value}")
    elif isinstance(value, list):
        print(f"  {key}: list with {len(value)} items")
    elif isinstance(value, dict):
        print(f"  {key}: dict with keys {list(value.keys())[:5]}...")
    else:
        print(f"  {key}: {type(value).__name__}")

# Look for project-related fields
print(f"\n=== Searching for project-related fields ===")
project_fields = ['folder', 'project', 'gizmo', 'workspace', 'category', 'tag', 'label', 'group']
for field in project_fields:
    found_keys = [k for k in all_keys if field.lower() in k.lower()]
    if found_keys:
        print(f"  Found '{field}': {found_keys}")

# Check user.json for project definitions
user_file = os.path.join(export_path, "user.json")
if os.path.exists(user_file):
    print(f"\n=== Checking user.json ===")
    with open(user_file, 'r') as f:
        user_data = json.load(f)
    print(f"Keys: {list(user_data.keys())}")

# Check if there's a separate projects file
for filename in os.listdir(export_path):
    if 'project' in filename.lower() or 'folder' in filename.lower():
        print(f"\n=== Found potential project file: {filename} ===")
        
# Look at conversation_template_id values (might be custom GPTs/projects)
print(f"\n=== Unique conversation_template_id values ===")
template_ids = {}
for conv in conversations:
    tid = conv.get('conversation_template_id')
    if tid:
        template_ids[tid] = template_ids.get(tid, 0) + 1

if template_ids:
    for tid, count in sorted(template_ids.items(), key=lambda x: -x[1])[:20]:
        print(f"  {tid}: {count} conversations")
else:
    print("  No conversation_template_id found")

# Check for any field that has multiple unique values (potential grouping)
print(f"\n=== Checking for grouping fields ===")
for key in ['async_status', 'is_archived', 'workspace_id']:
    if key in all_keys:
        unique_vals = set(conv.get(key) for conv in conversations)
        if len(unique_vals) > 1 and len(unique_vals) < 50:
            print(f"  {key}: {unique_vals}")
