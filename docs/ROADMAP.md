# Development Roadmap

*All features must be tested and type hinted.*

Handle line of sight in getting range. Can't draw line of sight through enemy entity.
Verify that range tracking is allowing first space diagonal. I'm only seeing melee attacks from orthogonal adjacency.


# TODO
I think I'm realizing that "You train that policy model to predict how much the action will increase the value prediction" doesn't work from only real game data (without using simulations) because
If you want to have accurate value estimates you must have low enough temperature that the models will play well. High temperature would be nearly a random winner 
But if you have low enough temperature then the model will settle into using the current preferred policy, and the training will only reinforce 'yes making that move made the value better' which should basically always be the case unless youre actively sabotaging yourself.
To get the value change for every move in the policy for more reasonable training I'd need to be making each move on a simulation, and at that point I think it's just alphazero with a sim depth of 1 which isn't simpler to implement than alphazero?

Value estimate training should be fine.
Regular play does not make sufficient game logs to train policy. Want to simulate the resulting state of all(?) actions
If we have hidden info/stochasticity handling then could do that in regular play and basically do an alphazero
On each turn take the highest policy action and take it. Also take all other possible actions as simulations and store those results as well.
In real play against a human don't need to make simulated turns.