# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Validated class-card transfer, independent of Tk and the system clipboard."""
import copy
from uuid import uuid4
from .i18n import tr
from . import uml_model

PREFIX = 'THONNY-SE-UML-CLASS\n'


def class_packet(document, cid):
    selected = {cid} if isinstance(cid,str) else set(cid or ())
    packet = uml_model.new_document()
    packet['classes'] = [copy.deepcopy(c) for c in document['classes'] if c['id'] in selected]
    if not packet['classes']:
        raise ValueError(tr('No class selected.'))
    selected = {c['id'] for c in packet['classes']}
    packet['relationships'] = [copy.deepcopy(r) for r in document['relationships']
                               if {r['start'],r['end']} <= selected]
    packet['comments'] = [copy.deepcopy(n) for n in document['comments'] if n['target'] in selected]
    return uml_model.validate(packet)


def insert_packet(document, packet, position=None):
    uml_model.validate(packet)
    if not packet['classes']:
        raise ValueError(tr('No class selected.'))
    original = packet['classes'][0]
    # Restrict untrusted clipboard content to this card and its owned objects.
    packet = class_packet(packet, {c['id'] for c in packet['classes']})
    ids = {}
    def collect(value):
        if isinstance(value, dict):
            if 'id' in value:ids.setdefault(value['id'],uuid4().hex)
            for v in value.values():collect(v)
        elif isinstance(value,list):
            for v in value:collect(v)
    collect(packet)
    def remap(value):
        if isinstance(value,dict):
            for key,v in value.items():
                if key in ('id','start','end','target','attribute') and isinstance(v,str) and v in ids:
                    value[key]=ids[v]
                else:remap(v)
        elif isinstance(value,list):
            for v in value:remap(v)
    remap(packet)
    names = {c['name'] for c in document['classes']}
    for card in list(packet['classes']):
        old_name = card['name']
        name,suffix = old_name,2
        reserved = names | {c['name'] for c in packet['classes'] if c['id']!=card['id']}
        while name in reserved:
            tail = str(suffix)
            name = old_name[:200-len(tail)]+tail
            suffix += 1
        if name != old_name:
            from .uml_relationships import renamed_class
            packet = renamed_class(packet,card['id'],name)
            next(c for c in packet['classes'] if c['id']==card['id']).pop('source',None)
        names.add(name)
    x,y = position if position is not None else (original['x']+32,original['y']+32)
    dx,dy = x-original['x'],y-original['y']
    objects = [*packet['classes'],*packet['comments']]
    dx=max(-min(o['x'] for o in objects),min(dx,1_000_000-max(o['x'] for o in objects)))
    dy=max(-min(o['y'] for o in objects),min(dy,1_000_000-max(o['y'] for o in objects)))
    for card in packet['classes']:
        card['x']+=dx;card['y']+=dy
    for note in packet['comments']:
        note['x']=max(0,min(1_000_000,note['x']+dx))
        note['y']=max(0,min(1_000_000,note['y']+dy))
    candidate = copy.deepcopy(document)
    for section in ('classes','relationships','comments'):
        candidate[section].extend(packet[section])
    return uml_model.validate(candidate),packet['classes'][0]['id']
