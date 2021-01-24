
from atlas.core.parameters import GLOBAL_PARAMETERS
from atlas.core.parameters import Parameters

def parse_params(conf:dict, scheduler) -> None:
    """Parse the parameters section of a config
    """
    if not conf:
        return
    params = Parameters(**conf)
    GLOBAL_PARAMETERS.update(params)