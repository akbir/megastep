import torch
from rebar import arrdict
from .. import spaces

__all__ = []

class FSMEnv:

    def __init__(self, states, n_envs, device='cuda'):
        indices = {n: i for i, n in enumerate(states)}
        (d_obs,) = {len(o) for t, o, ars in states.values()}
        (n_actions,) = {len(ars) for t, o, ars in states.values()}

        self.action_space = spaces.MultiDiscrete(1, n_actions)
        self.observation_space = spaces.MultiVector(1, d_obs) if d_obs else spaces.MultiEmpty()

        self.n_envs = n_envs
        self.n_agents = 1
        self.device = torch.device(device)
        self._token = torch.zeros(n_envs, dtype=torch.long)

        term, obs, trans, reward = [], [], [], []
        for t, o, ars in states.values():
            term.append(t)
            obs.append(o)
            trans.append([indices[s] for s, r in ars])
            reward.append([r for s, r in ars])
        self._term = torch.as_tensor(term, dtype=torch.bool, device=self.device)
        self._obs = torch.as_tensor(obs, dtype=torch.float, device=self.device)
        self._trans = torch.as_tensor(trans, dtype=torch.int, device=self.device)
        self._reward = torch.as_tensor(reward, dtype=torch.float, device=self.device)

    def reset(self):
        self._token[:] = 0
        return arrdict(
            obs=self._obs[self._token, None],
            reward=torch.zeros((self.n_envs,), dtype=torch.float, device=self.device),
            reset=torch.ones((self.n_envs), dtype=torch.bool, device=self.device),
            terminal=torch.ones((self.n_envs), dtype=torch.bool, device=self.device))

    def step(self, decision):
        actions = decision.actions[:, 0]
        reward = self._reward[self._token, actions]
        self._token[:] = self._trans[self._token, actions].long()
        
        reset = self._term[self._token]
        self._token[reset] = 0

        return arrdict(
            obs=self._obs[self._token, None],
            reward=reward,
            reset=reset,
            terminal=reset)

    def __repr__(self):
        s, a = self._trans.shape
        return f'{type(self).__name__}({s}s{a}a)' 

    def __str__(self):
        return repr(self)


class State:

    def __init__(self, name, builder):
        self._name = name
        self._builder = builder

    def obs(self, obs):
        self._builder._obs.add((self._name, obs))
        return self

    def to(self, action, state, reward=0., prob=1.):
        self._builder._trans.add((self._name, action, state, reward, prob))
        return self

class Builder:

    def __init__(self):
        self._obs = []
        self._trans = []

    def state(self, name):
        return State(name, self)


def fsm(f):

    def init(self, *args, n_envs=1, **kwargs):
        states = f(*args, **kwargs)
        super(self.__class__, self).__init__(states=states, n_envs=n_envs)

    name = f.__name__
    __all__.append(name)
    return type(name, (FSMEnv,), {'__init__': init})

@fsm
def UnitReward():
    return {'start': (False, (), [('start', 1.)]),}

@fsm
def Chain(n):
    assert n >= 2, 'Need the number of states to be at least 1'
    states = {}
    for i in range(n-2):
        states[i] = (False, (i/n,), [(i+1, 0.)])
    if n > 1:
        states[n-2] = (False, (n-2/n,), [(n-1, 1.)])
    states[n-1] = (True, (n-1/n,), [(n-1, 0.)])
    return states

# @fsm
# def CoinFlip():
#     return {
#         'start': (False, (0.,))
#         'heads': (False, (+1.,), [('end', +1.)]),
#         'tails': (False, (-1.,), [('end', -1.)]),
#         'end': (True, (0.,), [('end', 0.)])}