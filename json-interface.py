# This file defines a way to read from stdin a System followed by any number of UCA's
# The program will send this information to the solver and print the results to stdout 

from control import Action, conj, eq, FinTypeDecl, Ident, neg, System, Type, UCA, VarDecl, when
from control import uca_from_json, system_from_json
from solver import assertInvariants, checkConstraints, genAllowedScenarios, \
    genRequiredScenarios, setupYicesContext
from tycheck import buildTypingCtx, tycheckSystem, tycheckUCA, TypeError
from typing import Any, Dict, List, Mapping, Optional, Tuple
from yices import Config, Context, Model, Status, Types, Terms

def read_system() -> System:
    # Code to safely read in a system from json input
    # Potentially Fails with Error json message and exits the program
    try:
        sys_json: str = input()
    except EOFError:
        pass
    sys_opt: Optional[System] = system_from_json(sys_json)
    match sys_opt:
        case None: 
            print(sys_json)
            print('{"Error": "Unable to Parse System"}')
            exit(-1)
        case system: 
            sys:System = system
            return sys

def read_uca() -> Optional[UCA]:
    # Code to safely read in a UCA from json input
    # Potentially Fails with Error json message and exits the program
    # For now will return None when a message indicating the last uca has been sent is recieved 
    # TODO define the type of error message in message.py or something
    try:
        uca_json: str = input()
    except EOFError:
        pass
    if uca_json == "LAST_UCA":
        return None
    uca_opt: Optional[UCA] = uca_from_json(uca_json)
    match uca_opt:
        case None: 
            print('{"Error": "Unable to Parse UCA"}')
            exit(-1)
        case unsafe_control_actin: 
            uca:UCA = unsafe_control_actin
            return uca

if __name__ == "__main__":

    # Read in a system and a list of unsafe control actions 
    # Then run the solver aided stpa analysis
    sys:System = read_system()
    print(sys)
    ucas: List[UCA] = []
    while True:
        uca_opt = read_uca()
        match uca_opt:
            case None:
                break
            case uca: 
                ucas.append(uca)
    # At this point we should be guaranteed to have a list of uca's in ucas
    # The rest of this procedure is to call the functionality to pass the ucas and system to yices
    # Check that the system is well-formed.
    """
    try:
        ctx: Mapping[Ident, Type] = buildTypingCtx(sys)
        # tycheckSystem(sys, ctx)
        for u in ucas:
            tycheckUCA(u, ctx)
    except TypeError as err:
        print(err.msg)
        exit(-1)

    # Verify UCAs against system specification.
    yices_ctx, env, fintype_els = setupYicesContext(ctx, sys)
    assertInvariants(yices_ctx, env, sys)
    counterexample = checkConstraints(yices_ctx, ctx, env, fintype_els, sys, ucas)
    if counterexample:
        print('Failed to verify UCA. Counterexample:')
        print(counterexample)

    # TODO: This is making me wish the actions were labelled with their
    # full names... We could pretty easily implement a very basic renamer
    # pass that doesn't support imports or any interesting scoping logic
    # to fill in missing qualifiers, but I really would rather avoid that
    # for everything other than identifiers appearing in constraint
    # expressions...
    def printScenarios(system: System) -> None:
        def go(s: System, parent: Optional[Ident]) -> None:
            qualifier = Ident(parent, s.name)
            for a in s.actions:
                print("\nScenarios in which action '%s' is ALLOWED:" % Ident(qualifier, a.name))
                for scen in genAllowedScenarios(yices_ctx, ctx, env, fintype_els, a):
                    print(scen)
                print("\nScenarios in which action '%s' is REQUIRED:" % Ident(qualifier, a.name))
                for scen in genRequiredScenarios(yices_ctx, ctx, env, fintype_els, a):
                    print(scen)
            for c in s.components:
                go(c, qualifier)
        go(system, None)

    # printScenarios(sys)

    yices_ctx.dispose()
    """
