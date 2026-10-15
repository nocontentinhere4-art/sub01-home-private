"""Persist exact native fingerprint differences without changing acceptance rules."""
import json
from pathlib import Path


def differences(expected,actual,path='$'):
    if type(expected) is not type(actual):
        return [{'path':path,'expected':expected,'actual':actual}]
    if isinstance(expected,dict):
        rows=[]
        for key in sorted(set(expected)|set(actual)):
            child=path+'/'+str(key)
            if key not in expected:rows.append({'path':child,'expected_key_present':False,'actual':actual[key]})
            elif key not in actual:rows.append({'path':child,'expected':expected[key],'actual_key_present':False})
            else:rows.extend(differences(expected[key],actual[key],child))
        return rows
    if isinstance(expected,list):
        if len(expected)!=len(actual):return [{'path':path,'expected':expected,'actual':actual}]
        return [row for i,(a,b)in enumerate(zip(expected,actual))for row in differences(a,b,path+'/'+str(i))]
    return []if expected==actual else[{'path':path,'expected':expected,'actual':actual}]


def persist(target,expected,actual,context=None):
    rows=differences(expected,actual)
    payload={'schema':'sub01.exact-native-fingerprint-difference.v1','acceptance_changed':False,
             'differences':rows,'expected':expected,'actual':actual,'context':context or{}}
    path=Path(target);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,indent=2)+'\n')
    return rows
