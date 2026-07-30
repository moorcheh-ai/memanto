# -*- coding: utf-8 -*-
import json
import os

def list_conflicts(report_path):
    with open(report_path, 'r') as f:
        report = json.load(f)
    return [conflict for conflict in report if not conflict['resolved']]

def resolve_conflict(report_path, conflict_index):
    with open(report_path, 'r') as f:
        report = json.load(f)
    
    # Adjust the conflict index to account for resolved conflicts
    num_resolved_conflicts = sum(1 for conflict in report if conflict['resolved'])
    adjusted_conflict_index = conflict_index + num_resolved_conflicts
    
    # Resolve the conflict at the adjusted index
    conflict_to_resolve = report[adjusted_conflict_index]
    conflict_to_resolve['resolved'] = True
    
    # Delete the memories associated with the resolved conflict
    deleted_old = conflict_to_resolve['old']
    deleted_new = conflict_to_resolve['new']
    os.remove(os.path.join('memories', deleted_old))
    os.remove(os.path.join('memories', deleted_new))
    
    # Save the updated report
    with open(report_path, 'w') as f:
        json.dump(report, f)
    
    return {'deleted_old': deleted_old, 'deleted_new': deleted_new, 'status': 'resolved'}