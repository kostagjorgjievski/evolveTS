"""Concrete wire examples; these provide no scientific answers or evidence."""
import json

HYPOTHESIS_EXAMPLE = {
    'mechanism': 'Describe the source-backed mechanism in plain text.',
    'expected_opportunity': 'If this method transfers, it may reduce cost; this is not a measured result.',
    'first_test': 'Describe the cheapest falsifying test for the reproducer.',
    'source_urls': ['EXACT_URL_RETURNED_BY_FETCH_SOURCE'],
}
PACKET_EXAMPLE = {
    'hypothesis_id': 'ID_RETURNED_BY_PROPOSE_HYPOTHESIS',
    'mechanism': 'Describe the mechanism.',
    'code_sections': 'Cached source path and relevant function or section names.',
    'compatibility': 'Known compatible interfaces and remaining checks.',
    'uncertainty': 'Explicit unresolved scientific questions.',
    'first_test': 'Cheapest discriminating test; Kimi will execute it.',
    'rejection_conditions': 'Observed result that would reject this direction.',
    'next_action': 'Independently review sources, then run the first test.',
    'evidence_spans': [{'source_url': 'EXACT_FETCHED_TEXT_URL',
                        'quote': 'REPLACE_WITH_VERBATIM_CACHED_TEXT',
                        'claim': 'What this actual quotation supports.'}],
    'dependency_urls': [],
}
SCOUT_HANDOFF_GUIDANCE = (
    '\nHANDOFF WIRE FORMAT: Call tools with JSON arguments matching these shapes. '
    'All prose fields are STRINGS, not objects. Arrays contain plain strings, '
    'never {"item": ...} wrappers. Do not paste the placeholders below as evidence.\n'
    'propose_hypothesis example: '+json.dumps(HYPOTHESIS_EXAMPLE)+'\n'
    'check_scout_packet and record_scout_packet use THE SAME complete shape: '
    +json.dumps(PACKET_EXAMPLE)+'\n'
    'Once check_scout_packet passes, submit that exact packet to record_scout_packet '
    'and finish; do not spend another checkpoint polishing it. A saved draft alone '
    'does not enter the reproducer queue. Remaining scientific uncertainty belongs '
    'in uncertainty/first_test, not in repeated prose revisions. Do not add unrelated '
    'mechanism comparisons after a viable handoff is ready. '
    'If a URL is missing, read the actual fetch receipt: retain exact path, encoding '
    'and version query. A similarly named URL is not equivalent. Binary artifacts '
    'may be dependencies; quote their fetched textual README/manifests as evidence. '
    'Never invent quotations or treat source-reported scores as our measurements.\n'
)
