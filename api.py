# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from conflict_resolver import resolve_conflict

app = Flask(__name__)

@app.route('/api/v2/agents/1/conflicts', methods=['GET'])
def get_conflicts():
    report_path = 'test_report.json'
    conflicts = [conflict for conflict in json.load(open(report_path, 'r')) if not conflict['resolved']]
    return jsonify(conflicts)

@app.route('/api/v2/agents/1/conflicts/resolve', methods=['POST'])
def resolve_conflict_api():
    report_path = 'test_report.json'
    conflict_index = request.json['conflict_index']
    result = resolve_conflict(report_path, conflict_index)
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)