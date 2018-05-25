import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import scipy.stats as sps
from scipy.stats import rv_continuous
import scipy.optimize as spo
from scipy.integrate import quad
import inspect
import JMCtools.common as c
import JMCtools.six as six # Python 2 & 3 compatibility tools

class ListModel:
    """
    Base class for freezable statistics objects (similar to those in scipy.stats)
    that are built from lists of scipy.stats (or similar) objects 
    """
    def __init__(self, submodels, parameters=None, frozen=False):
        """If parameters!=None, will freeze this model and assume that all submodels are frozen too"""
        self.N_submodels = len(submodels)
        self.parameters = parameters
        if self.parameters==None or self.parameters==False:
            self.frozen = False
        else:
            self.frozen = True
        # Alternatively can manually set frozen=True if all submodels
        # are supplied pre-frozen
        if frozen is True:
            self.frozen = True

        # Determine number of variates associated with each submodel
        # If multivariate the submodel should be supplied as a tuple
        # (model, dims) where dims gives the number of variates that
        # will be generated by model.rvs
        # If model is not frozen this could change, it is true, but
        # in practice I don't think we need to account for this. It's 
        # a pretty weird corner case.
        self.dims = []
        self.submodels = []
        for s in submodels:
            try:
                (m,d) = s
            except TypeError as e:
                m = s
                d = 1
            self.dims += [d]
            self.submodels += [m]
        #print('self.dims:',self.dims)
 
    def _check_parameters(self, parameters=None):
        """Validate and return parameters
           Note that this is just the parameters of *this* object,
           which might be e.g. mixing parameters. Parameters
           of the submodels don't need to be supplied if they
           are supposed to be frozen, so we don't store them
           here in that case.
        """
        if self.frozen and parameters!=None:
            raise ValueError("This distribution is frozen! You are not permitted to alter the parameters used to compute the pdf of a frozen distribution object.")
        elif not self.frozen and parameters==None:
            raise ValueError("This distribution is not frozen, but no parameters were supplied to compute the pdf! Please provide some.")
        elif self.frozen and parameters==None:
            parameters = self.parameters
        elif not self.frozen and parameters!=None:
            pass # just use what was passed in 
        # Check that here are we have parameters for all submodels
        # Ok no, that isn't really what this function is for.
        #if len(parameters)!=len(self.submodels):
        #    raise ValueError("Parameter list supplied to JointModel (len={0}) is not the same length as the number of submodels (len={1})! We need parameters for all submodels!".format(len(parameters),len(self.submodels)))
        return parameters

    def _freeze_submodels(self, parameters):
        """Get list of all submodels, frozen with the supplied parameters"""
        if self.frozen:
            raise ValueError("This distribution is already frozen! You cannot re-freeze it with different parameters")
        else:
            out_submodels = []
            for submodel, pars in zip(self.submodels,parameters):
                out_submodels += [submodel(**pars)] # Freeze all submodels
        return out_submodels

    def split_data(self,samples):
        """Split a numpy array of data into a list of sub-arrays to be passed to independent
        submodel objects.
        Components must be indexed by last dimension of 'samples' array"""
        return c.split_data(samples,self.dims)

# Handy class for sampling from mixture models in scipy.stats
class MixtureModel(ListModel):
    def __init__(self, submodels, weights=None, *args, **kwargs):
        super().__init__(submodels, weights)

    def __call__(self, weights=None, parameters=None):
        """Construct a 'frozen' version of the distribution
           Need to fix all parameters of all submodels if doing this.
        """
        if self.frozen:
            raise ValueError("This distribution is already frozen! You cannot re-freeze it with different parameters")
        self._check_parameters(parameters)
        weights = self._check_parameters(weights)
        frozen_submodels = self._freeze_submodels(parameters)
        return MixtureModel(frozen_submodels, weights) # Copy of this object, but frozen

    def pdf(self, x, weights=None, parameters=None):
        x = np.array(x)
        self._check_parameters(parameters)
        weights = self._check_parameters(weights)

        if weights==None:
            raise ValueError("No mixing weights supplied!")
        if parameters==None:
            parameters = [{} for i in range(len(self.submodels))]
        try:
            #print("parameters:",parameters)
            _pdf = weights[0] * np.exp(self.submodels[0].logpdf(x,**parameters[0]))
        except AttributeError:
            _pdf = weights[0] * np.exp(self.submodels[0].logpmf(x,**parameters[0]))
        for w,submodel,pars in zip(weights[1:],self.submodels[1:],parameters[1:]):
            try:
                _pdf += w*np.exp(submodel.logpdf(x,**pars))
            except AttributeError:
                _pdf += w*np.exp(submodel.logpmf(x,**pars))
        return _pdf
    
    def logpdf(self, *args, **kwargs):
        return np.log(self.pdf(*args,**kwargs)) # No better way to do this for mixture model

    def rvs(self, size, weights=None, parameters=None):
        #print('MixtureModel.rvs: ', weights, parameters)
        self._check_parameters(parameters)
        weights = self._check_parameters(weights)
        if weights==None:
            raise ValueError("No mixing weights supplied!")
        if parameters==None:
            parameters = [{} for i in range(len(self.submodels))]
        #print("weights:", weights, ", size:", size)
        submodel_choices = np.random.choice(range(len(self.submodels)), p=weights, size=size)[...,np.newaxis]
        submodel_samples = np.array([submodel.rvs(size=size,**pars) for submodel,pars in zip(self.submodels,parameters)])

        #print("submodel_choices.shape:", submodel_choices.shape)
        #print("submodel_samples.shape:", submodel_samples.shape)
  
        _rvs = np.choose(submodel_choices, submodel_samples)
        #print("_rvs.shape:",_rvs.shape)
        # # ahh crap, need to apply this in a more fancy way due to possible crazy nested structure of submodel_samples
        # # So, we are choosing elements from the top level list
        # # In other words, we have multiple crazy nested list structures, and we want to decend them and pull out the
        # # correct elements, and mix them back together. I think better off masking the bottom level arrays, and then
        # # "adding" them. I think the nested structures must match or else the mixture model wouldn't make sense. Need
        # # to be unable to tell which mixture submodel the sample came from, so they must have identical structure.
        # def mask_chosen(A,choices,i):
        #    return A * (choices==i) # Non-zero only in selected elements
        # #print("submodel_choices.shape:", submodel_choices.shape)
        # submodel_selections = [ list(c.apply_f(lambda A: A * (submodel_choices==i), submodel_rvs)) for i,submodel_rvs in enumerate(submodel_samples) ]
        # #print("submodel_selections:", submodel_selections)
        # _rvs = list(c.apply_f(lambda *arrays: sum(arrays), *submodel_selections))
        #print("_rvs:", _rvs) 
        #print("Mixture rvs output:", c.get_data_structure(_rvs))
        return _rvs

class PowerMixtureModel(rv_continuous):
    def __init__(self, submodels, weights, domain, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.submodels = submodels
        self.weights = weights
        self.norm = 1
        self.domain = domain
        # Need to compute normalisation factor
        # Can do this numerically, but need user to specify the domain to use
        # No discrete distributions allowed, for now.
        # Also only mixtures of 1D models are allowed for now.
        res = quad(self.pdf,*self.domain) # this is a problem if we want to allow parameters to change...
        self.norm = res[0]
        #print "self.norm = ",self.norm
        
    def pdf(self, *args, **kwargs):
        return np.exp(self.logpdf(*args,**kwargs))
   
    def get_norm(self, x, weights=None, parameters=None):
        """Compute normalisation for pdf for many parameters in parallel (possibly)"""
        # do it by Monte Carlo integration?
        # Even if data vector is long, should only have to do this once for a given array of parameters
     
        # We are going to use 'x' to determine the shape of the parameter array
        # This means that 'x' must be input after it is already broadcasted against
        # other parameters etc. 
        # TODO: Finish this? It is pretty hard... don't actually need x here,
        # but need to somehow infer which direction of the parameter array actually
        # represent varying parameter values. We don't want to re-do the MC integration
        # for directions in which it is the data that changes. But that is hard to
        # infer from the parameter arrays alone.

        # tol = 0.001
        # Nbatch = 1000 # Number of random numbers per parameter point per iteration
        # while err > tol:
        #     # Generate batch of random numbers in self.domain
        #     for low,high in self.domain:
        #        np.random.uniform(low,high,s

        # self.pdf(x, weights, parameters) 

    def logpdf(self, x, weights=None, parameters=None):
        if weights==None:
            weights = self.weights # TODO check if frozen
        if parameters==None:
            parameters = [{} for i in range(len(self.submodels))]
        _logpdf = weights[0] * self.submodels[0].logpdf(x,**parameters[0])
        for w,submodel,pars in zip(weights[1:],self.submodels[1:],parameters[1:]):
            _logpdf += w * submodel.logpdf(x,**pars)
        return _logpdf - np.log(self.norm)
        
    def rvs(self, size):
        raise ValueError("Sorry, random samples cannot be drawn from this distribution, it is too freaky")
        # TODO: If the computation of the norm via MC integration is implemented, then it basically gives a set of samples
        # from the distribution at the same time. So these functions should be semi-combined.
        return None
    
class JointDist(ListModel):
    """Class for constructing a joint pdf from independent pdfs, which can be sampled from.
       Has a feature for overriding the pdf of submodels so that, for example, portions of
       the joint pdf may be profiled or marginalised analytically to speed up fitting routines.
    """
    def __init__(self, submodels, parameters=None, submodel_logpdf_replacements=None, *args, **kwargs):        
        # Need some weird stuff for Python 2 and 3 compatibility
        if issubclass(ListModel, object):
            # new style class, call super
            super(JointDist, self).__init__(submodels,parameters,*args,**kwargs)
        else:
            # old style class, call __init__ manually
            ListModel.__init__(self,submodels,parameters,*args,**kwargs)
        #super().__init__(submodels, parameters,*args,**kwargs)
        # Here we DO need to store the submodel parameters, because we sometimes use them to evaluate
        # analytic replacements for the pdfs of the submodels

        if submodel_logpdf_replacements==None:
            self.submodel_logpdf_replacements = [None for i in range(len(self.submodels))]
        else:
            self.submodel_logpdf_replacements = submodel_logpdf_replacements
     

    def split(self,selection):
        """Create a JointDist which is a subset of this one, by splitting off the submodels 
           with the listed indices into a separate object"""
        if self.frozen:
            out = JointDist([(self.submodels[i],self.dims[i]) for i in selection],
                          parameters = [self.parameters[i] for i in selection],
                          frozen = True,
                          submodel_logpdf_replacements = [self.submodel_logpdf_replacements[i] for i in selection]
                         )
        else:
            # If not frozen, cannot supply parameters
            out = JointDist([(self.submodels[i],self.dims[i]) for i in selection],
                          frozen = False,
                          submodel_logpdf_replacements = [self.submodel_logpdf_replacements[i] for i in selection]
                         )
        return out
 
    def __call__(self, parameters=None):
        """Construct a 'frozen' version of the distribution
           Need to fix all parameters of all submodels if doing this.
        """
        if self.frozen:
            raise ValueError("This distribution is already frozen! You cannot re-freeze it with different parameters")
        parameters = self._check_parameters(parameters)
        frozen_submodels = self._freeze_submodels(parameters)
        return JointDist(frozen_submodels, parameters, self.submodel_logpdf_replacements) # Copy of this object, but frozen

    def submodel_logpdf(self,i,x,parameters={}):
        """Call logpdf (or logpmf) of a submodel, automatically detecting where parameters
           should come from"""
        if self.frozen and parameters!={}:
           raise ValueError("This distribution is frozen! You are not permitted to alter the parameters used to compute the pdf of a frozen distribution object.")
        elif not self.frozen and parameters=={}:
           raise ValueError("This distribution is not frozen, but no parameters were supplied to compute the pdf! Please provide some.")
        #print("Inspecting submodel[{0}]:".format(i))
        #print(self.submodels[i].__doc__) # Just checking that the correct object is called!
        #print("calling submodels[{0}].logpdf({1},**{2})".format(i,x,parameters))
        try:
             _logpdf = self.submodels[i].logpdf(x,**parameters)
        except AttributeError:
             _logpdf = self.submodels[i].logpmf(x,**parameters)
        return _logpdf 

    def submodel_pdf(self,i,x,parameters=None):
        return np.exp(self.submodel_logpdf(i,x,parameters))

    def pdf(self, x, parameters=None):
        """Provide data to pdf as a list of arrays of same
           length as the submodels list. Each array will be
           passed straight to those submodels, so broadcasting
           can be done at the submodel level. 
           This does mean that JointModel behaves DIFFERENTLY
           to "basic" distribution functions from scipy. So
           you should not construct JointModels with JointModels
           as submodels. Just make a new one from scratch in that
           case, since the submodels have to be statistically
           independent anyway.
           NOTE: could make a special constructor for JointModel
           to merge together pre-existing JointModels.

           parameters - list of dictionaries of parameters to be
           passed to the submodel pdf functions. If submodel is
           'frozen' then its corresponding element of 'parameters'
           should be an empty dictionary.
        """
        # Validate the supplied parameters (if any)
        parameters = self._check_parameters(parameters)
        #print("parameters:",parameters) 
        x_split = self.split_data(x) # Convert data array into list of data for each submodel
        # Use first submodel to determine pdf array output shape
        if self.submodel_logpdf_replacements[0]!=None:
            _pdf = np.exp(self.submodel_logpdf_replacements[0](x_split[0],**parameters[0]))
        else:
            _pdf = self.submodel_pdf(0,x_split[0],parameters[0])
        # Loop over rest of the submodels
        for i,(xi,submodel,alt_logpdf,pars) in enumerate(zip(x_split[1:],self.submodels[1:],self.submodel_logpdf_replacements[1:],parameters[1:])):
            #print(pars)
            if alt_logpdf!=None:
                _pdf *= np.exp(alt_logpdf(xi,**pars))
            else:
                _pdf *= self.submodel_pdf(i+1,xi,pars)
        return _pdf
    
    def logpdf(self, x, parameters=None):
        """As above but for logpdf
        """
        _logpdf_list = self.logpdf_list(x,parameters)
        _logpdf = 0
        for l in _logpdf_list:
            _logpdf += l
        return _logpdf
 
    def logpdf_list(self, x, parameters=None):
        """list of logpdfs of all submodels
        """
        parameters = self._check_parameters(parameters)
       #print("x_in.shape:", x_in.shape)
        x_split = self.split_data(np.atleast_2d(x)) # Convert data array into list of data for each submodel
        #for i,x_i in enumerate(x):
        #    #print("x_{0}.shape: {1}".format(i,x_i.shape))
        #    #print("self.dims[{0}]: {1}".format(i,self.dims[i]))
        #    if x_i.shape[-1] != self.dims[i]:
        #        raise ValueError("Failed to correctly separate data into correct size for submodel {0}! The ith data component has {1} variates, but we expected {2}!".format(i,x_i.shape[-1],self.dims[i]))
        #print("JointModel.logpdf (with {0} submodels) called with parameters:".format(len(self.submodels)))
        #for i,s in enumerate(parameters):
        #    print(" submodel {0}:".format(i))
        #    for key,val in s.items():
        #        print("  {0}: {1}".format(key,val))
        # If pdf is frozen, need to 'mute' parameters for submodels whose pdf's have not been replaced by analytic expressions 
        if parameters == None:
            parameters = [{} for i in range(len(self.submodels))]
        if self.frozen:
            for i in range(len(self.submodels)):
                if self.submodel_logpdf_replacements[i]==None:
                    parameters[i] = {}
        #print("JointModel.logpdf: x = ",x)
        #print("JointModel.logpdf: structure(x) = ", c.get_data_structure(x))
        #print("len(self.submodels):",len(self.submodels))
        # Use first submodel to determine pdf array output shape
        _logpdf = []
        if self.submodel_logpdf_replacements[0]!=None:
            _logpdf += [self.submodel_logpdf_replacements[0](x_split[0],**parameters[0])]
        else:
            _logpdf += [self.submodel_logpdf(0,x_split[0],parameters[0])]
        # Loop over rest of the submodels
        if len(self.submodels)>1:
            for i,(xi,submodel,alt_logpdf,pars) in enumerate(zip(x_split[1:],self.submodels[1:],self.submodel_logpdf_replacements[1:],parameters[1:])):
                #print('submodel:',i+1)
                #print('pars:',pars)
                #print('xi:',xi)
                if alt_logpdf!=None:
                    _logpdf += [alt_logpdf(xi,**pars)]
                else:
                    _logpdf += [self.submodel_logpdf(i+1,xi,pars)]
        #print("_logpdf.shape:",_logpdf.shape)
        return _logpdf
    
    def set_submodel_logpdf(self, i, f):
        """Replace the logpdf function for the ith submodel"""
        self.submodel_logpdf_replacements[i] = f

    def set_logpdf(self, listf):
        """Replace the logpdf for all submodels (use 'None' for elements where
        you want to keep the original pdf"""
        self.submodel_logpdf_replacements = listf

    def rvs(self, size, parameters=None):
        """Output will be a list of length N, where N is the number
        of random variables in the joint PDF. Each element will be an array of shape
        'size', possibly with extra dimensions if submodel is multivariate. That is, each variable is drawn
        with 'size', and the results are joined into a list."""
        #print("in rvs:", parameters)
        if self.frozen:
            parameters = [{} for i in range(len(self.submodels))]
        else:   
            parameters = self._check_parameters(parameters)
        _rvs = []
        for i,(submodel, pars) in enumerate(zip(self.submodels,parameters)):
            try:
               #print("in JointDist.rvs, submodel[{0}], pars={1}".format(i,pars)) 
               _rvs += [submodel.rvs(size=size,**pars)]
            except TypeError as e:
               # Python 3 only
               #raise TypeError("Encountered error while evaluating submodel.rvs for submodel {0} with parameters {1}.".format(i,list(pars.keys()))) from e
               # Python 2 compatible, but lose traceback
               raise TypeError("Encountered error while evaluating submodel.rvs for submodel {0} with parameters {1}.".format(i,list(pars.keys())))

        # Previously had this. I expanded it out for improved error checking.
        #_rvs = [submodel.rvs(size=size,**pars) for submodel, pars in zip(self.submodels,parameters)]
       
        # NEW: Want to return this as one array, so that it behaves exactly like scipy.stats objects
        # and so that it doesn't matter what the underlying objects are, the data feeds through just
        # the same.
        # In scipy.multivariate the dimension that indexes the random variable components is the last
        # one, so we need to stack the rvs results along the last dimension.

        #print("Shapes:") 
        #for X in _rvs:
        #    print(X.shape)
        size = np.atleast_1d(size)
        newsize = tuple(list(size) + [-1])
        out = np.concatenate([a.reshape(*newsize) for a in _rvs],axis=-1) #Make sure number of dimensions is correct
        #print("out.shape:", out.shape)
        return out

class TransDist:
    """Transform a probability distribution into a different parameterisation
       Todo: implement frozen-ness
    """
    
    def null_transform(self,**kwargs):
        """Default null parameter transformation. Useful if only a simple
           renaming is required, which can be done via 'renaming_map'"""
        return kwargs

    def __init__(self,orig_dist,transform_func=None,renaming_map=None,func_args=None):
        """renaming_map should be a list of string instructions
           like
            ['a -> b', 'x -> y']
           which indicated parameter 'a' should be called as 'b'
           in the transform_func, and so on.
        """
        self.transform_func = transform_func
        self.orig_dist = orig_dist
        renaming = {}
        if renaming_map is not None:
            for item in renaming_map:
                try:
                   key,val = item.split(' -> ')
                   renaming[key] = val
                except ValueError:
                   print("Failed to parse parameter remapping instruction (Did you remember to pass these instructions as a list?)")
                   raise
        self.renaming_map = renaming
        # Try to figure out what arguments we need, so we can
        # tell other objects when they ask (they can't inspect
        # the logpdf function directly since it takes arbitrary
        # arguments!)
        if func_args is None:
           if self.transform_func is None:
               # No transform func supplied, so we are using the Null transformation
               self.transform_func = self.null_transform
               # Inspect the underlying distribution object for parameters
               fargs = c.get_dist_args(self.orig_dist)
           else:
               # Inspect the transformation function for arguments
               fargs = c.get_func_args(self.transform_func)
           # Performing any renaming requested by renaming_map
           self.args = []
           for arg in fargs:
               if arg in self.renaming_map.values():
                   key = [k for k,val in self.renaming_map.items() if val==arg][0] # get first match
                   self.args += [key]
               else:
                   self.args += [arg]
        else:
           self.args = func_args
        # Sanity check
        if len(self.args)==0:
           raise ValueError("Failed to find any arguments for this\
 distribution! You may need to supply them explictly via the 'func_args'\
 argument. Debug information:\n\
    orig_dist      = {0}\n\
    transform_func = {1}\n\
    renaming_map   = {2}\n\
    func_args      = {3}\n\
".format(orig_dist,transform_func,renaming_map,func_args))
        #print("self.args:", self.args)

    def rvs(self, size, **parameters):
        """Generate random samples from the distribution"""
        orig_pars = self.get_orig_args(**parameters)
        try:
            samples = self.orig_dist.rvs(size=size,**orig_pars)
        except TypeError:
            six.reraise(TypeError,TypeError("Failed to run 'rvs' member function of distribution {0}, using arguments {1} (which are derived from {2} using function {3}).".format(self.orig_dist, orig_pars, parameters, self.transform_func)))
        return samples
    
    def get_orig_args(self,**parameters):
        """Compute parameters for the original distribution using the
           reparameterisation"""
        # Need to take into account possible renaming:
        renamed_parameters = {}
        for key, val in parameters.items():
            if key in self.renaming_map.keys():
                renamed_parameters[self.renaming_map[key]] = val
            else:
                renamed_parameters[key] = val
        #print('input parameters:', parameters)
        #print('self.renaming_map:',self.renaming_map)
        #print('get_orig_args returns:', renamed_parameters)
        return self.transform_func(**renamed_parameters)

    # Which of logpmf or logpdf actually works will depend
    # on which one exists in the underlying distribution
    def logpmf(self, x, **parameters):
        orig_pars = self.get_orig_args(**parameters)
        return self.orig_dist.logpmf(x,**orig_pars) 

    def logpdf(self, x, **parameters):
        orig_pars = self.get_orig_args(**parameters)
        return self.orig_dist.logpdf(x,**orig_pars)
