# -*- coding: utf-8 -*-
"""
Superclass and subclasses for synthesizers.

The superclass Synthesizer() is a template for real synthesizer classes.


Notes
=====

Reference
---------

Superclass prototype
--------------------

This approach was recommended by Barzia Tehrani on 2012 Oct 14, 11:36 am:
'I have seen Instantiate helper methods just to bridge the gap between
different languages.'

Logging levels
--------------::
 * DEBUG Detailed information, typically of interest only when diagnosing problems.
 * INFO  Confirmation that things are working as expected.
 * WARNING   An indication that something unexpected happened, or indicative of some problem in the near future (e.g. ‘disk space low’). The software is still working as expected.
 * ERROR   Due to a more serious problem, the software has not been able to perform some function.
 * CRITICAL  A serious error, indicating that the program itself may be unable to continue running.

Things to do
------------
# Move SG() class from __init__.py in here.
"""
import logging
from time import sleep
from MonitorControl import ClassInstance, ObservatoryError
from Electronics.Instruments import Synthesizer
import valon_synth as vs
from Data_Reduction import nearest_index

#mylogger = logging.getLogger("__main__."+__name__)
module_logger = logging.getLogger(__name__)

############################## Valon Synthesizers #############################

synth = {}
synth[1] = vs.SYNTH_A
synth[2] = vs.SYNTH_B

class Valon5007(vs.Synthesizer):
  """
  Actual dual-output Valon synthesizer unit

  Queried parameters are remembered as instance parameters.

  Notes
  =====

  Operation
  ---------
  Documentation in the module itself is rather sparse.  The best can be found
  at wiki below.  However, the internal functioning, and therefore effective
  use of the device, is not clear.  This is what I've been able to figure out.
  
  For each synthesizer chain, the output frequency is the VCO frequency divided
  by 2^n, 0 <= n <= 4::
   
           f
            VCO
    f    = -----,  0 <= n <= 4.
     out     n
            2
   
  This is not under the user's direct control.  The VCO range must be set
  so that the above is true for the desired frequency.

  There is a counter that counts VCO cycles. When a certain count is reached,
  a pulse is sent to the phase-frequency detector (PFD).  So the PFD
  operates at a frequency of::
   
            f
             VCO
    f    = ------
     PFD   n
            count
   
  This is compared to a reference frequency from an internal or external
  reference.  options[0:3] affect the reference frequency;
  options[0] doubles the reference frequency, if True.
  options[1] halves the reference frequency, if True.
  options[2] is an integer by which the reference frequency is divided.

  Note that sending a pulse creates a frequency comb at intervals of the
  the PFD frequency which appear in the VCO output as 'spurs'.  The
  'spurs' can be minimized with options[3], presumably at the cost of lock
  stability.

  The output frequency can be restricted to set separated by some
  channel spacing df.  The channel spacing is an optional parameter in the
  set_frequency() method. (The default is 10 MHz.)  This is done by taking
  the nearest integer of the PFD frequency,::
   
                      ( f    )
                      (  PFD )
    f         = round (------)
     PFD,chan         ( df   )
   
  which is called 'mod' on the NRAO wiki page.  Since the PFD frequency is the
  reference frequency or a multiple of it, it cannot be arbitrarily shifted.
  So the PFD must accept an offset of::
   
    df    = f    - f
      PFD    PFD    PFD,chan
   
  On the NRAO wiki page, the offset is given in terms of the VCO frequency,
  called 'frac'::
   
                     f
                      PDF
    df    = n      * ----
      VCO    count    df
   
  So the VCO frequency will be::
                                       (            df     )
                                       (              VCO  )
    f    = n      * ( f    + df    ) = ( n      + ---------) * f
     VCO    count   (  PFD     PFD )   (  count   f        )    PFD
                                       (           PFD,chan)

  Most of this is not under the user's control.  The things the user controls
  or specifies are::
      f   , f   , df, f       , f       , and options[0:4].
       ref   out       VCO,min   VCO,max
  By the way, there is a note of the NRAO wiki that set_reference() doesn't
  work for the interbal reference and, of course, has no impact on an external
  reference.
  
  Documentation
  -------------
  https://github.com/nrao/ValonSynth/wiki
  http://www.altera.com/support/devices/pll_clock/basics/pll-basics.html
  """
  def __init__(self, timeout=None):
    """
    Initialize the Valon5007 object
    """
    module_logger.debug("Initializing Valon5007")
    vs.Synthesizer.__init__(self,"/dev/ttyUSB0")
    self.conn.setTimeout(timeout)
    module_logger.debug("valon_synth.Synthesizer initialized")
    # These are the minimum attributes of a Synthesizer
    self.__get_tasks__ = {"frequency":  self.get_frequency,
                          "rf_level":   self.get_rf_level,
                          "phase lock": self.get_phase_lock}
    self.__set_tasks__ = {"frequency":  self.set_frequency,
                          "rf_level":   self.set_rf_level}
    self.freq = {}
    self.pwr = {}
    self.lock = {}
    # These are specific to the Valon5007
    self.__get_tasks__["label"] =      self.get_label
    self.__get_tasks__["VCO range"] =  self.get_vco_range
    self.__get_tasks__["options"] =    self.get_options
    self.__set_tasks__["label"] =      self.set_label
    self.__set_tasks__["VCO range"] =  self.set_vco_range
    self.__set_tasks__["options"] =    self.set_options
    self.status = {1:{}, 2:{}}
    self.options = {}
    self.vco_range = {}
    self.name = {}
    # Initialize attributes
    for synth_id in [1,2]:
      self.update_synth_status(synth_id)
    module_logger.debug("__init__(): done")

  def shown_parameters(self):
    pars = self.__get_tasks__.keys()
    pars.sort()
    return pars
    
  def update_synth_status(self,synth_id):
    """
    Update all the status data

    @param synth_id : 1 or 2
    @type  synth_id : int

    @return:None
    """
    module_logger.debug("Getting status for synth "+str(synth_id))
    for param in self.__get_tasks__.keys():
      self.get_p(param,synth_id)
    return self.status[synth_id]
    
  def __unicode__(self):
    return "Valon5007"

  def get_p(self, param, synth_id):
    """
    Re-read the specified parameter

    @param param : name of the parameter
    @type  param : str

    @param synth_id : 1 or 2, as on datasheet
    @type  synth_id : int

    @return: requested parameter
    """
    s = synth[synth_id]
    module_logger.debug("get_p: (synthesizer %d %d): %s",synth_id,s,param)
    module_logger.debug("get_p: task %s",str(self.__get_tasks__[param]))
    self.status[synth_id][param] = self.__get_tasks__[param](s)
    module_logger.debug("get_p: result: %s",self.status[synth_id][param])
    return self.status[synth_id][param]

  def set_p(self, param, synth_id, *args, **kwargs):
    """
    Re-read the specified parameter

    @param param : name of the parameter
    @type  param : str

    @param synth_id : 1 or 2, as on datasheet
    @type  synth_id : int

    @return: requested parameter
    """
    module_logger.debug("Called set_p with %s, %s",str(args),str(kwargs))
    s = synth[synth_id]
    if param == "rf_level":
      # This is a fix for the valon_synth.Synthesizer() method
      # which just returns False if you don't give a valid key.
      # This returns the nearest key.
      pkeys = self.rfl_rev_table.keys()
      pkeys.sort()
      best_key = nearest_index(pkeys,args[0])
      args = (pkeys[best_key],)
    try:
      success = self.__set_tasks__[param](s,*args,**kwargs)
    except Exception, detail:
      raise Exception(param,"set failed")
    else:
      sleep(0.1)
      if success:
        self.status[synth_id][param] = self.__get_tasks__[param](s)
        return self.status[synth_id][param]
      else:
        raise ObservatoryError(param,"setting failed")

class Valon1(Synthesizer):
  """
  Each output of the Valon 5005 is treated as a logically separate
  synthesizer
  """
  instance_exists = False
  def __init__(self, timeout=None):
    """
    Instantiate a synthesizer using Valon 5005 channel 1

    Any parameters pertaning to the hardware can be queried as self.hw.method()
    """
    self.hw = Valon5007(timeout=timeout)
    self.status = self.hw.status[1]
    Valon1.instance_exists = True

  def get_p(self,param):
    """
    Get a synthesizer parameter

    @param param : name of the parameter
    @type  param : str

    @return: requested parameter
    """
    return self.hw.get_p(param, 1)

  def set_p(self,param,*args,**kwargs):
    """
    Get a synthesizer parameter

    @param param : name of the parameter
    @type  param : str

    @return: requested parameter
    """
    return self.hw.set_p(param, 1, *args, **kwargs)

  def update_synth_status(self):
    """
    Refresh all the configuration parameters
    """
    return self.hw.update_synth_status(1)

  def __unicode__(self):
    """
    Return identifier
    """
    return "Valon5007 synth 1"

class Valon2(Synthesizer):
  """
  Each output of the Valon 5005 is treated as a logically separate
  synthesizer
  """
  instance_exists = False
  def __init__(self,timeout=None):
    """
    Instantiate a synthesizer using Valon 5005 channel 1

    Any parameters pertaining to the hardware can be queried as self.hw.method()
    """
    self.hw = Valon5007(timeout=timeout)
    self.status = self.hw.status[2]

  def get_p(self,param):
    """
    Get a synthesizer parameter

    @param param : name of the parameter
    @type  param : str

    @return: requested parameter
    """
    return self.hw.get_p(param, 2)

  def set_p(self,param, *args, **kwargs):
    """
    Get a synthesizer parameter

    @param param : name of the parameter
    @type  param : str

    @return: requested parameter
    """
    return self.hw.set_p(param, 2, *args, **kwargs)

  def update_synth_status(self):
    """
    Refresh all the configuration parameters
    """
    return self.hw.update_synth_status(2)

  def __unicode__(self):
    """
    Return identifier
    """
    return "Valon5007 synth 2"

############################## tests ################################

if __name__ == "__main__":
  a = ClassInstance(Synthesizer,Valon1)
  print "Synthesizer",a.__unicode__()
  print a.get_p("label"), "frequency is", a.get_p("frequency"),"MHz"
  print a.update_synth_status()

  b = ClassInstance(Synthesizer,Valon2)
  print "Synthesizer",b.__unicode__()
  print b.get_p("label"), "frequency is", b.get_p("frequency"),"MHz"
  print b.update_synth_status()

  # This will raise an error
  try:
    d = ClassInstance(Synthesizer,Agilent)
  except NameError, details:
    print "Synthesizer NameError:",details