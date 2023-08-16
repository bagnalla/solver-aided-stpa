I've been toying around with a little proof-of-concept verifier for
UCAs / control action constraints. It's based on a very high-level
model of control systems, similar to how they're presented in the STPA
handbook. There are no process model variables or behavioral models of
the actual control algorithms, so it doesn't do any kind of 'deep'
verification of the actual system behavior. It just provides an aid to
the STPA analyst who is coming up with controller safety constraints
based on the high-level control structure and UCAs identified in the
STPA process. You might call this approach "solver-aided controller
constraint specification".

# The basic idea

1. The analyst goes through the usual STPA process specifying losses,
system-level hazards and constraints, the control structure, and
UCAs. Of these, only the control structure and UCAs are formalized
(although they should contain references to associated hazards/losses
for traceability).

2. Next is to specify constraints on individual control actions that
when enforced will prevent the UCA hazards. One way to obtain these is
to simply negate the UCAs, but as the STPA handbook says it's not
necessary to have a one-to-one correspondence between UCAs and
controller constraints. E.g., a single constraint might rule out
multiple UCAs. However, the analyst might make a mistake at this step
and create a constraint that doesn't quite rule out the UCA(s) as
intended. A solver can check automatically that the constraints do
indeed rule out the UCAs, or otherwise provide a counterexample system
state where the given constraints are satisfied but a UCA is still
possible.

# The value provided by the verifier

- Formalizing the control system and constraints/assumptions forces
  the analyst to be think clearly and precisely about the analysis and
  to state all assumptions explicitly.

- The tool validates the model to ensure that it's well-formed.

- The tool catches logical mistakes made by the analyst when creating
  controller action constraints.

- Maybe the tool could make recommendations to fix constraints?
  Perhaps via some clever use of interpolants (supported by yices).

- If all the UCAs are verified successfully (proved impossible under
  the control action constraints), the tool can generate system states
  that are compatible with the constraints to help the analyst
  consider possibly hazardous scenarios that they may have missed,
  i.e., to discover more UCAs.

- The solver can be used iteratively and interactively. E.g., when the
  analyst adds a new UCA, the tool will immediately point out a
  hazardous scenario corresponding to the UCA that needs to be handled
  by a constraint. Then when a sufficient constraint is added, the
  tool can be used to look for more UCAs, and so on.

# System data structures

The following definitions are in [control.py](control.py).

## Actions

An action is just a name for the action and a list of constraints
where each constraint is a Boolean expression:

```python
class Action:
    name:        str        # Name of action (e.g., CA1).
    constraints: List[Expr] # Safety constraints on action.
```

## Components

A component (perhaps should be called 'Entity' or something since it's
used to represent all parts of the system including things like the
environment) is represented by the following:

```python
class Component:
    name:       str           # Name of component.
    state:      List[VarDecl] # Internal state of component.
    invariants: List[Expr]    # Invariant properties of internal state.
    actions:    List[Action]  # Control actions that can be performed
                              # by this component.
```

The internal state of a component is a list of variables, each with a
specified type (currently 'bool', 'int', or an enum type). The
invariant is a property of the internal state that is expected to
always hold (for example, two variables of the state might always be
related in some way).

## Systems

```python
class System:
    types:        List[TypeDecl]  # Type declarations.
    components:   List[Component] # A collection of components.
    assumptions:  List[Expr]      # Global system assumptions.
```

The type declarations are for declaring enum types. The assumptions
are like component state invariants but are global so they can express
relations between different components.

## UCAs

```python
UCAType = Literal['issued', 'not issued']
class UCA:
    component: str     # Name of controller.
    action:    str     # Name of action.
    type:      UCAType # Type of UCA.
    context:   Expr    # Context in which action is potentially hazardous.
```

Currently only the first two types of UCAs are supported, but I think
the other two can actually be simulated via these two so they may be
the only ones necessary.

# Example system

The following is a small example system specified in a hypothetical
concrete syntax (a parser for this syntax isn't implemented -- the
system is currently encoded directly in the above data structures in
the file [run.py](run.py)).

```
system aircraft_brakes_system:
  type DryOrWet: {dry, wet}
  component aircraft:
    var landing: bool
    action hit_brakes:
      constraint: wheels.weight_on_wheels is true
  component environment:
    var runway_status: DryOrWet
  component wheels:
    var weight_on_wheels: bool
  assumption:
     when aircraft.landing is true and environment.runway_status is dry,
       wheels.weight_on_wheels is true
```

And a couple UCAs:

```
UCA aircraft.hit_brakes:
  type: issued
  context: wheels.weight_on_wheels is false
UCA aircraft.hit_brakes:
  type: not issued
  context: aircraft.landing is true
```

Running the verifier on the above system and UCAs (run `make` to
reproduce) produces the following output (see [solver.py](solver.py)
for the code that compiles expressions and invokes the yices solver):

```
Checking UCA(action='hit_brakes', type='issued', context=UnaryExpr(op='NOT', e=NameExpr(qualifier='wheels', name='weight_on_wheels')))
UCA verified!
Checking UCA(action='hit_brakes', type='not issued', context=NameExpr(qualifier='aircraft', name='landing'))
Failed to verify UCA. Counterexample:
(= landing true)
(= weight_on_wheels false)
(= runway_status wet)
```

# UCA verification

The solver does the following for each UCA of type 'issued' (where the
action is potentially hazardous when issued in the given context):

- Attempt to prove that the conjunction of all the constraints (and
  invariants/assumptions) implies the negation of the UCA context.
  
- If successful, this means that the constraints do indeed rule out
  the hazard specified by the UCA.
  
- If unsuccessful, print out a system state in which all the
  constraints are satisfied but the hazard specified by the UCA is
  still possible.

And for each UCA of type 'not issued' (where the action is potentially
hazardous when **NOT** issued in the given context):

- Attempt to prove that the UCA context (again under the
  invariants/assumptions) implies the conjunction of all the
  constraints.

- If successful, this means that no constraint ever prevents the
  action from being executed in the context specified by the UCA.

- If unsuccessful, print out a system state in which the UCA context
  is satisfied (and so it would be hazardous to not execute the
  action) but also violates one of the constraints which prohibits it
  from being executed.

The two types of UCAs are verified differently because there's only
one type of constraint. It might be necessary to include a second type
of constraint corresponding to 'when not issued' UCAs, i.e.,
constraints that specify when it is safe to **NOT** issue the
action. Then we can perform a symmetric verification of the UCAs
wrt. those constraints as well.
