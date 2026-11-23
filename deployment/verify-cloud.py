"""Exercise the deployed API without printing or embedding private access keys."""
import argparse
import json
import math
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = 'https://last-of-our-league-dedf75.indiasouthcentral.cloudapp.azure.com'
APP = 'https://nifty-research-terminal.nearbydrape.chatgpt.site'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', action='store_true')
    parser.add_argument('--expect-ready', action='store_true')
    args = parser.parse_args()
    keys = json.loads((ROOT / 'paper/cloud-access/private-access.json').read_text())

    def call(path, name=None, method='GET', origin=APP, expected=200):
        headers = {'Origin': origin}
        if name:
            headers['Authorization'] = 'Bearer ' + name + '.' + keys[name]['key']
        data = b'{}' if method == 'POST' else None
        if data:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(ORIGIN + path, data=data, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            assert response.code == expected, (path, response.code, expected)
            if origin == APP:
                assert response.headers.get('Access-Control-Allow-Origin') == APP
            return json.load(response)

    assert call('/healthz')['mode'] == 'paper'
    call('/api/health', expected=401)
    call('/api/health', 'madhan', origin='https://untrusted.example', expected=403)
    owner = call('/api/health', 'madhan')
    viewer = call('/api/health', 'friend')
    assert owner['execution'] == 'cloud' and owner['permissions']['control']
    assert not viewer['permissions']['control']
    call('/api/automation/start', 'friend', 'POST', expected=403)
    account = call('/api/dashboard', 'madhan')
    paper = account['paper']
    assert paper['initial_capital_rs'] == 500000
    assert paper['closed_trades'] >= 1 and paper['open_trades'] in (0, 1)
    assert math.isfinite(paper['realised_equity_rs'])
    if not paper['open_trades']:
        assert abs(paper['realised_equity_rs'] - paper['initial_capital_rs'] - paper['net_closed_pnl_rs']) < .02
    assert not paper['orders_submitted']
    if args.start:
        call('/api/automation/start', 'madhan', 'POST')
    health = call('/api/health', 'madhan')
    assert health['automation'].get('state') not in ('error', 'data_error', 'stopped')
    if args.expect_ready:
        assert health['operations']['ready'] and health['version'] == '1.2.1'
    print(json.dumps({'https_verified': True, 'authentication_verified': True,
                      'cors_verified': True, 'viewer_control_rejected': True,
                      'closed_trades': paper['closed_trades'], 'open_trades': paper['open_trades'],
                      'equity_rs': paper['realised_equity_rs'], 'paper_orders': len(paper.get('orders', [])),
                      'automation': health['automation']}, indent=2))


if __name__ == '__main__':
    main()
