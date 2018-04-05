"""Common helper tools"""

# def apply_f(f,a):
#     """Apply some function to 'bottom level' objects in a nested structure of lists,
#        return the result in the same nested listed structure.
#        Credit: https://stackoverflow.com/a/43357135/1447953
#     """
#     if isinstance(a,list):
#         return map(lambda u: apply_f(f,u), a)
#     else:
#         return f(a)
# 
# def apply_f_binary(f,a,b):
#     """Apply some binary function to matching 'bottom level' objects 
#        in mirrored nested structure of lists,
#        return the result in the same nested listed structure.
#     """
#     # We have to descend both list structures in lock-step!
#     if isinstance(a,list) and isinstance(b,list):
#         return map(lambda u,v: apply_f_binary(f,u,v), a, b)
#     else:
#         return f(a,b)

# Generalisation of the above to any number of arguments
def apply_f(f,*iters):
    """Apply some function to matching 'bottom level' objects 
       in mirrored nested structure of lists,
       return the result in the same nested listed structure.
       'iters' should be 
    """
    # We have to descend both list structures in lock-step!
    if all(isinstance(item,list) for item in iters):
        return list(map(lambda *items: apply_f(f,*items), *iters))
    elif any(isinstance(item,list) for item in iters):
        raise ValueError("Inconsistency in nested list structure of arguments detected! Nested structures must be identical in order to apply functions over them")
    else:
        return f(*iters)

def almost_flatten(A):
    """Flatten array in all except last dimension"""
    return A.reshape((-1,A.shape[-1]))

def get_data_slice(x,i,j=None):
    """Extract a single data realisation from 'x', or a numpy 'slice' of realisations
       This harder than it sounds because we don't know what object structure
       we are dealing with. For example the JointModel to which we interface
       could be built from a bunch of different MixtureModels which are themselves 
       made out of JointModels, so that the actual data arrays are buried in
       a complicated list of lists of structure. We need to descend through these
       lists, pluck a data realisation out of every "bottom level" array, and
       put everything back together in the same list structure. And we need to
       do it pretty efficiently since we're going to have to iterate through these 
       slices.
    """
    data, size = x
    if j==None:
       data_slice = list(apply_f(lambda A: almost_flatten(A)[i,:],data))
       slice_length = 1
    else:
       data_slice = list(apply_f(lambda A: almost_flatten(A)[i:j,:],data))
       slice_length = j-i
    return data_slice, (slice_length,size[-1])

def get_data_structure(x):
    """Report the nested structure of a list of lists of numpy arrays"""
    return list(apply_f(lambda A: A.shape, x))
 
