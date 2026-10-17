"""Synthetic fault/read-back exercise of the actual resource recovery functions."""
import json
import os
from pathlib import Path
import sys
from mtgmeta.resource_progress import ResourceProgress, save
from tools.delivery import resource_recovery as recovery
from tools.delivery.github import GitHub

root=Path(os.environ['RUNNER_TEMP'])/'resource-probe'
root.mkdir(exist_ok=True)
origin={'repository':os.environ['GITHUB_REPOSITORY'],'operation':'behavior-v2-resource-cloud',
        'source':os.environ['GITHUB_SHA'],'run':int(os.environ['GITHUB_RUN_ID']),
        'attempt':int(os.environ['GITHUB_RUN_ATTEMPT']),'workflow':'.github/workflows/prepare-pages.yml'}
def entry(kind,n):
    if kind=='localization':
        return {'query':['Synthetic card '+str(n)],'page':1},json.dumps({'page':1,'total_pages':1,'items':[{'name':'Synthetic card '+str(n)}]}).encode()
    return {'image':f'https://cards.scryfall.io/normal/{n}.jpg'},b'\xff\xd8\xff\xe0synthetic-verified-image\xff\xd9'

mode=sys.argv[1]
for kind in ('localization','mtgo-landing-card-image-cache'):
    work=root/kind
    if mode=='prepare':
        state=ResourceProgress(work,{'kind':kind})
        for n in range(1,11):
            key,payload=entry(kind,n)
            def fetch():
                if n==7:
                    (work/'seventh.part').write_bytes(b'incomplete')
                    raise OSError('Intentional seventh resource failure')
                return payload
            try: state.bytes(key,fetch,lambda b:recovery.validate_entry(state.state['identity'],key,b))
            except OSError:
                assert n==7 and len(state.state['entries'])==6
                break
        certificate=root/'certificate.pem'
        certificate.write_text(os.environ['HANDOFF_CERT'])
        recovery.seal(work,root/(kind+'.cms'),certificate,origin)
    elif mode=='preserve':
        key=root/'key.pem'
        key.write_text(os.environ['ARCHIVE_HANDOFF_KEY'])
        key.chmod(0o600)
        try:
            bundle=root/(kind+'.zip')
            recovery.decrypt(root/(kind+'.cms'),bundle,key,origin=origin)
            client=GitHub('Jacelber/mtgo-data-releases',token_env='ARCHIVE_TOKEN')
            source_run=GitHub(origin['repository']).api(f'repos/{origin["repository"]}/actions/runs/{origin["run"]}')
            result=recovery.preserve_private(bundle,client,origin=origin,source_run=source_run)
            save(root/(kind+'-preserved.json'),result)
            print(json.dumps(result))
        finally: key.unlink(missing_ok=True)
    elif mode=='resume':
        # A separate workflow invocation has no original runtime directory.
        assert not work.exists()
        client=GitHub('Jacelber/mtgo-data-releases',token_env='ARCHIVE_TOKEN')
        result=recovery.resume_private(client,work,repository=origin['repository'],operation=origin['operation'],builder=kind)
        assert result['state']=='restored_inputs'
        state=ResourceProgress(work,{'kind':kind})
        assert len(state.state['entries'])==6 and not list(work.glob('*.part'))
        calls=[]
        for n in range(1,11):
            key,payload=entry(kind,n)
            def fetch():
                calls.append(n)
                return payload
            state.bytes(key,fetch,lambda b:recovery.validate_entry(state.state['identity'],key,b))
        assert calls==[7,8,9,10] and state.reused==6
        result.update(reused=state.reused,requested=calls,bad_partial_reused=False)
        save(root/(kind+'-resumed.json'),result)
        print(json.dumps(result))
    else: raise ValueError(mode)
