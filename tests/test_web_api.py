"""Authoritative web sessions over the original engines."""
import copy
import unittest

from fastapi.testclient import TestClient

from echelon import web_api
from echelon.expanded_recording import verify as verify_expanded
from echelon.recording import replay_battle


class WebApiTests(unittest.TestCase):
    def setUp(self):
        web_api.sessions = web_api.SessionStore(limit=8, ttl=3600)
        self.client = TestClient(web_api.app)

    def create(self, **options):
        response = self.client.post('/api/games', json=options)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_config_and_lightweight_opponents(self):
        self.assertEqual(self.client.get('/api/health').json(), {'status': 'ok'})
        config = self.client.get('/api/config').json()
        self.assertEqual(config['classic_opponents'][:2], ['random', 'heuristic'])
        self.assertEqual(config['draft']['gold'], 13000)
        self.assertEqual(config['draft']['units']['cavalry']['manpower'], 10)

    def test_classic_creation_turns_and_illegal_order(self):
        game = self.create(human_army='Red', first_army='Blue', opponent='random',
                           deployment='random', seed=19)
        self.assertEqual(game['state']['active_army'], 'Red')
        self.assertEqual(len(game['history']), 1)
        key = game['id']
        response = self.client.post(f'/api/games/{key}/orders', json={
            'unit_id': 'R-I', 'kind': 'ADVANCE', 'target': [99, 99]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get(f'/api/games/{key}').json()['state'], game['state'])
        response = self.client.post(f'/api/games/{key}/orders', json=game['legal_orders'][0])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['history']), 3)
        self.assertEqual(response.json()['state']['active_army'], 'Red')

    def test_drafting_and_expanded_creation(self):
        bought = self.client.post('/api/draft/purchase', json={'roster': [], 'kind': 'infantry'})
        self.assertEqual(bought.json()['remaining'], [11000, 35, 3])
        refunded = self.client.post('/api/draft/remove', json={'roster': ['infantry'], 'index': 0})
        self.assertEqual(refunded.json()['roster'], [])
        self.assertEqual(self.client.post('/api/draft/purchase', json={
            'roster': ['infantry'] * 3, 'kind': 'infantry'}).status_code, 422)
        preview = self.client.post('/api/draft/preview', json={
            'roster': ['cavalry'] * 3 + ['infantry'], 'doctrine': 'balanced',
            'human_army': 'Red', 'seed': 42})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()['remaining'], [500, 5, 0])
        self.assertTrue(preview.json()['ai_roster'])
        invalid = self.client.post('/api/draft/preview', json={'roster': ['infantry'] * 4})
        self.assertEqual(invalid.status_code, 422)
        game = self.create(ruleset='Expanded', human_army='Red', first_army='Blue',
                           opponent='cavalry', deployment='random',
                           roster=['infantry', 'infantry', 'cavalry', 'artillery'], seed=42)
        self.assertEqual(len(game['state']['units']), 8)
        self.assertEqual(game['state']['active_army'], 'Red')
        self.assertEqual(len(game['history']), 1)
        self.assertEqual(len(game['rosters']['Red']), 4)

    def test_requests_cannot_supply_engine_state_or_incompatible_modes(self):
        for body in ({'state': {'winner': 'Blue'}},
                     {'ruleset': 'Expanded', 'deployment': 'random', 'opponent': 'ppo', 'roster': ['infantry']},
                     {'ruleset': 'Classic', 'roster': ['cavalry']},
                     {'ruleset': 'Expanded', 'deployment': 'fixed', 'opponent': 'balanced', 'roster': ['infantry']}):
            self.assertEqual(self.client.post('/api/games', json=body).status_code, 422)
        game = self.create()
        self.assertEqual(self.client.post(f"/api/games/{game['id']}/orders", json={
            **game['legal_orders'][0], 'state': {'winner': 'Blue'}}).status_code, 422)

    def test_determinism_and_session_isolation(self):
        a = self.create(seed=31, deployment='random')
        b = self.create(seed=31, deployment='random')
        self.assertNotEqual(a['id'], b['id'])
        self.assertEqual(a['state'], b['state'])
        self.client.post(f"/api/games/{a['id']}/orders", json=a['legal_orders'][0])
        self.assertEqual(self.client.get(f"/api/games/{b['id']}").json()['state'], b['state'])

    def test_both_sides_finish_and_export_replays(self):
        for ruleset, army in (('Classic', 'Blue'), ('Classic', 'Red'),
                              ('Expanded', 'Blue'), ('Expanded', 'Red')):
            request = {'ruleset': ruleset, 'human_army': army, 'first_army': 'Red',
                       'opponent': 'heuristic' if ruleset == 'Classic' else 'balanced',
                       'deployment': 'fixed' if ruleset == 'Classic' else 'random',
                       'seed': 12}
            if ruleset == 'Expanded':
                request['roster'] = ['cavalry', 'cavalry', 'cavalry', 'infantry']
            game = self.create(**request)
            key = game['id']
            self.assertEqual(self.client.get(f'/api/games/{key}/replay').status_code, 409)
            steps = 0
            while not game['state']['finished']:
                orders = game['legal_orders']
                chosen = next((o for o in orders if o['kind'] == 'ATTACK'),
                              next((o for o in orders if o['kind'] == 'ADVANCE'), orders[0]))
                response = self.client.post(f'/api/games/{key}/orders', json=chosen)
                self.assertEqual(response.status_code, 200, response.text)
                game = response.json()
                steps += 1
                self.assertLessEqual(steps, 30)
            replay = self.client.get(f'/api/games/{key}/replay').json()
            self.assertEqual(replay['final']['winner'], game['state']['winner'])
            self.assertEqual(replay['version'] if ruleset == 'Expanded' else 1,
                             2 if ruleset == 'Expanded' else 1)
            if ruleset == 'Expanded': verify_expanded(replay)
            else: replay_battle(replay)

    def test_session_bounds_and_expiry(self):
        web_api.sessions = web_api.SessionStore(limit=1, ttl=60)
        old = self.create()
        new = self.create(seed=43)
        self.assertEqual(self.client.get(f"/api/games/{old['id']}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/games/{new['id']}").status_code, 200)
        game, _ = web_api.sessions.sessions[new['id']]
        web_api.sessions.sessions[new['id']] = (game, 0)
        self.assertEqual(self.client.get(f"/api/games/{new['id']}").status_code, 404)


if __name__ == '__main__':
    unittest.main()
