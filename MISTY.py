from __future__ import print_function

import datetime
import getpass
import os.path
import time

import numpy as np
from astropy.io import fits
import astropy.units as u

import trident

os.sys.path.insert(0, '/Users/molly/Dropbox/misty/MISTY-pipeline/spectacle')
#from spectacle.analysis.statistics import delta_v_90, equivalent_width
#from spectacle.analysis import Resample

ldb = trident.LineDatabase('lines.txt')
## ldb = trident.LineDatabase('atom_wave_gamma_f.dat')

def write_header(ray, start_pos=None, end_pos=None, lines=None, **kwargs):
    # begin making fits header
    prihdr = fits.Header()
    prihdr['AUTHOR'] = kwargs.get("author", getpass.getuser())
    prihdr['DATE'] = datetime.datetime.now().isoformat()
    prihdr['REDSHIFT'] = kwargs.get('redshift', 0.0)
    prihdr['RAYSTART'] = str(start_pos[0]).strip(' unitary') + ", " + \
        str(start_pos[1]).strip(' unitary') + ", " + str(start_pos[2]).strip(' unitary')
    prihdr['RAYEND'] = str(end_pos[0]).strip(' unitary') + ", " + \
        str(end_pos[1]).strip(' unitary') + ", " + str(end_pos[2]).strip(' unitary')
    prihdr['SIM_NAME'] = ray.basename
    prihdr['SIMSUITE'] = 'FOGGIE'
    prihdr['NLINES'] = str(len(np.array(lines)))
    prihdr['DOI'] = "doi.peeples2020.paper.thisistotesnotmadeup"
    prihdr['PAPER'] = "Peeples et al. (2020) RNAAS, ###, ###"
    prihdr['EUVB'] = "HM12_SS"  # probably shouldn't be hardcoded
    prihdr['IMPACT'] = (kwargs.get("impact", "undef"), "impact parameter, kpc")
    prihdr['ANGLE'] = (kwargs.get("angle", "undef"), "radians")

    prihdr['HALONAME'] = (kwargs.get('haloname','undef'))
    prihdr['MVIR'] = (kwargs.get('Mvir','undef'), 'Msun')
    prihdr['RVIR'] = (kwargs.get('Rvir','undef'), 'kpc')
    prihdr['MSTAR'] = (kwargs.get('Mstar','undef'), 'Msun')
    prihdr['MISM'] = (kwargs.get('Mism','undef'), 'Msun')
    prihdr['SFR'] = (kwargs.get('SFR','undef'), 'Msun yr^-1')

    lines = ldb.parse_subset(lines)

    i = 1
    for line in lines:
        keyword = 'LINE_' + str(i)
        prihdr[keyword] = line.name
        i += 1
    prihdu = fits.PrimaryHDU(header=prihdr)
    sghdulist = fits.HDUList([prihdu])
    return sghdulist


def write_parameter_file(ds, filename=None, hdulist=None):
    if type(hdulist) != fits.hdu.hdulist.HDUList:
        raise ValueError(
            'Must pass HDUList in order to write. Call write_header first.')

    # is a filename given? then use that
    if filename != None and os.path.isfile(filename):
        param_file = np.genfromtxt(filename, delimiter='=', dtype=str,
                                   autostrip=True)
        col1 = fits.Column(name='PARAMETERS', format='A50',
                           array=param_file[:, 0])
        col2 = fits.Column(name='VALUES', format='A50', array=param_file[:, 1])
    else:
        #  use ds.parameters
        col1 = fits.Column(name='PARAMETERS', format='A50',
                           array=list(ds.parameters.keys()))
        col2 = fits.Column(name='VALUES', format='A50',
                           array=[str(x) for x in ds.parameters.values()])

    col_list = [col1, col2]
    cols = fits.ColDefs(col_list)
    sghdr = fits.Header()

    sghdr['SIM_CODE'] = ds.dataset_type
    print("---> SIM_CODE set to ", ds.dataset_type,
          "if you don't like this, change it!")
    sghdr['COMPUTER'] = 'pleiades'
    print("---> ASSUMING PLEIADES FOR NOW BUT SHOULD BE PASSED IN")

    # primary_hdu = fits.PrimaryHDU(header=sghdr)

    sghdu = fits.BinTableHDU.from_columns(cols, header=sghdr)
    hdulist.append(sghdu)

    return sghdu


def generate_line(ray, line, zsnap=0.0, write=False, use_spectacle=True, hdulist=None, **kwargs):
    '''
    input: a trident lightray and a line; writes info to extension of hdulist
    '''
    if write and type(hdulist) != fits.hdu.hdulist.HDUList:
        raise ValueError(
            'Must pass HDUList in order to write. Call write_header first.')

    if not isinstance(line, trident.Line):
        ldb = trident.LineDatabase('lines.txt')
        # ldb = trident.LineDatabase('atom_wave_gamma_f.dat')
        line_out = ldb.parse_subset(line)
        print(line, line_out)
        line_out = line_out[0]

    ar = ray.all_data()
    lambda_rest = line_out.wavelength
    if line_out.name == "H I 1216":
        padding = 7.
    else:
        padding = 7.
    lambda_min = lambda_rest * (1 + min(ar['redshift_eff'])) - padding
    lambda_max = lambda_rest * (1 + max(ar['redshift_eff'])) + padding

    # using dv
    halfdv = kwargs.get('halfdv', 500.)  # km/s
    pixdv = kwargs.get('pixdv', 0.2) # km/s

    sg = trident.SpectrumGenerator(lambda_min=-1.0*halfdv,
                                   lambda_max=halfdv,
                                   dlambda=pixdv,  # km/s
                                   bin_space='velocity',
                                   line_database='lines.txt'
                                #   line_database='atom_wave_gamma_f.dat'
                                   )
    sg.make_spectrum(ray, lines=line_out.name, min_tau=1.e-5,
                     store_observables=True)

    if write and str(line_out) in sg.line_observables_dict:
        tau = sg.tau_field
        flux = sg.flux_field
        disp = sg.lambda_field  ## this is now a velocity
        velocity = np.array(disp)*u.Unit('km/s')
        with u.set_enabled_equivalencies(u.equivalencies.doppler_relativistic(lambda_rest*u.Unit('Angstrom')*(1+zsnap))):
            wavelength = velocity.to('Angstrom')
        redshift = (wavelength / (lambda_rest* u.Unit('Angstrom')) - 1)

        z_col = fits.Column(name='redshift', format='E', array=redshift)
        vel_col = fits.Column(name='velocity', format='E',
                                 array=disp, unit='km/s')
        tau_col = fits.Column(name='tau', format='E', array=tau)
        flux_col = fits.Column(name='flux', format='E', array=flux)
        col_list = [z_col, vel_col, tau_col, flux_col]

        #for key in sg.line_observables_dict[str(line_out)].keys():
        #    col = fits.Column(name='sim_' + key, format='E',
        #                      array=sg.line_observables_dict[str(line_out)][key])
        #    col_list = np.append(col_list, col)

        cols = fits.ColDefs(col_list)
        sghdr = fits.Header()
        sghdr['LINENAME'] = line_out.name
        print("----->>>>using ", line_out.name,
              "as LINENAME, whereas ", line, " was passed. Change?")
        sghdr['RESTWAVE'] = (line_out.wavelength, "Angstroms")
        sghdr['F_VALUE'] = line_out.f_value
        sghdr['GAMMA'] = line_out.gamma
        print ("f = ", line_out.f_value)

        # want to leave blank spaces now for values that we're expecting to generate for MAST
        # first let's add some spaces for the simulated, tau-weighted values!
        sghdr['SIM_TAU_HDENS'] = -9999.
        sghdr['SIM_TAU_TEMP'] = -9999.
        sghdr['SIM_TAU_METAL'] = -9999.
        sghdr['TOT_COLUMN'] = (np.log10(np.sum(
            sg.line_observables_dict[line_out.identifier][
                'column_density'].value)), "log cm^-2")

        # we're also going to want data from spectacle
        if use_spectacle:
            print(sg.line_list[0])

            lines_properties = get_line_info(disp, flux, \
                                            tau=sg.tau_field, redshift=zsnap, \
                                            lambda_0=sg.line_list[0]['wavelength'].value, \
                                            f_value=sg.line_list[0]['f_value'], \
                                            gamma=sg.line_list[0]['gamma'], \
                                            ion_name=line_out.name)
            for key in lines_properties:
                sghdr[key] = lines_properties[key]

        sghdu = fits.BinTableHDU.from_columns(
            cols, header=sghdr, name=line_out.name)

        hdulist.append(sghdu)

    return sg


def get_line_info(disp, flux, **kwargs):
    '''
    runs spectacle on a trident spectrum object and returns absorber properties
    '''
    import astropy.units as u
    from scipy.signal import argrelextrema
    from spectacle.analysis.line_finding import LineFinder

    plot = kwargs.get('plot',False)
    threshold = kwargs.get('threshold', 0.01)
    redshift = kwargs.get("redshift", 0.0)
    tau = kwargs.get("tau", -1.0*np.log(flux))  ## if you aren't passing tau in,
                                                ## you probably don't want to solve using tau
    disp = disp * u.Unit('Angstrom')

#    if np.min(flux) > (1-threshold):
#        return {}
    if sum(f < (1-threshold) for f in flux) < 3:
        print("not enough absoprtion!!!")
        return {}

    lsf = kwargs.get('lsf', None)  # this should be the full model

    ## if line info is not passed in, assume Lya
    ion_name = kwargs.get("ion_name", "H I 1216")
    lambda_0 = kwargs.get("lambda_0", 1215.6701)
    f_value = kwargs.get("f_value", 0.416400)
    gamma = kwargs.get("gamma", 6.265e8)

    with u.set_enabled_equivalencies(u.equivalencies.doppler_relativistic(lambda_0*u.Unit('Angstrom')*(1+redshift))):
        velocity = disp.to('km/s')

    # This process will find lines in the trident spectrum
    # and assign the values set in the `defaults` dict to
    # the new lines found.

    # Create a dictionary to hold the default values we want
    # the lines to have
    default_values = dict(
        lambda_0=lambda_0 * u.Unit('Angstrom'),
        f_value=f_value,
        gamma=gamma,
        bounds={
            'column_density': (10, 23), # Global bounds in log,
            'v_doppler': (2, 500.) # Global bounds in km/s
            }
        )

    # Have the line finder attempt to find absorption features. Fit the
    # result to the data.
    print('*~*~*~*~*~> setting up the LineFinder *~*~*~*~*~>')
    print('length of arrays:', len(disp), len(velocity), len(flux))
    line_finder = LineFinder(rest_wavelength=lambda_0 * u.Unit('Angstrom'),
                             redshift=0,
                             data_type='flux',
                             defaults=default_values,
                             threshold=threshold, # flux decrement has to be > threshold; default 0.01
                             min_distance=2. * u.Unit('km/s'), # The distance between minima, in dispersion units!
                             max_iter=3000, # The number of fitter iterations; reduce to speed up fitting at the cost of possibly poorer fits
                             lsf=lsf
                             )
    print('*~*~*~*~*~> running the fitter now *~*~*~*~*~>')
    try:
        spec_mod = line_finder(velocity, flux)
        print('line_finder worked!')
        if plot:
            # Plot for visual checks
            import matplotlib.pyplot as plt
            from uuid import uuid4

            f, ax = plt.subplots()

            ax.plot(disp, flux)
            ax.plot(disp, line_finder._result_model.flux(disp))
            ax.plot(disp, spec_mod.flux(disp))

            plt.savefig("{}.png".format(uuid4()))

        line_properties = {
            'NCOMP': len(spec_mod.line_models)
        }

        # Calculate total equivalent width -- RESTFRAME!
        tot_ew = equivalent_width(disp/(1+redshift), flux, continuum=1.0)
        tot_dv90 = delta_v_90(disp/(1+redshift), flux, continuum=1.0, rest_wavelength=lambda_0 * u.Unit('Angstrom'))

        line_properties.update({
            'totEW': (tot_ew.value, tot_ew.unit.to_string()),
            'totdv90': (tot_dv90.value, tot_dv90.unit.to_string())
        })

        # Loop over identified absorption regions and calculate the ew and dv90
        # for the region
        for i, reg in enumerate(spec_mod.regions):
            mask = [(velocity > velocity[reg[0]]) & (velocity < velocity[reg[1]])]
            reg_flux = flux[mask]
            reg_Nmin = np.size(np.where(reg_flux[argrelextrema(reg_flux, np.less)[0]] < (1-threshold)))

            reg_dv90 = delta_v_90(velocity[mask]/(1+redshift), flux[mask], continuum=1.0,
                                  rest_wavelength=default_values['lambda_0'])
            reg_ew = equivalent_width(velocity[mask]/(1+redshift), flux[mask], continuum=1.0)

            if not np.isnan(reg_ew.value):
                line_properties.update({
                    'regEW{}'.format(i): (reg_ew.value, reg_ew.unit.to_string()),
                    'regdv90{}'.format(i): (reg_dv90.value, reg_dv90.unit.to_string()),
                    'regNmin{}'.format(i): reg_Nmin
            })

        line_properties.update({
            'NREG': len(spec_mod.regions)
        })

        comp_table = spec_mod.stats(velocity)
        comp_table.sort('delta_v')
        print(comp_table)

        # Loop over individual ions and calculate per-ion properties
        for i, line in enumerate(comp_table):
            line_properties.update({
                'fitcol' + str(i): (line['col_dens'], 'log cm/s'),
                'fitb' + str(i): (line['v_dop'].value, line['v_dop'].unit.to_string()),
                'fitvcen' + str(i): (line['delta_v'].value, line['delta_v'].unit.to_string()),
                'fitEW' + str(i): (line['ew'].value, line['ew'].unit.to_string()),
                'fitdv90' + str(i): (line['dv90'].value, line['dv90'].unit.to_string()),
                'fitfwhm' + str(i): (line['fwhm'].value, line['fwhm'].unit.to_string())
            })

    except:
         print("***** --->> line finding SO did not work ****")
         return {}

    return line_properties


def get_trident_ray(ds, ray_start, ray_end, line_list, **kwargs):
    '''
    input: simulation dataset, the ray start and end points, and the line list;
    returns: the trident ray with the physical information we want to keep track of
    '''
    out_tri_name = kwargs.get('out_tri_name', "temp.h5")
    ## first, figure out the fields
    field_list = ['metallicity', 'H_p0_number_density']

    ## now, to make sure we have the relevant info for the relevant lines

    ## now, make the ray
    triray = trident.make_simple_ray(ds, start_position=ray_start.copy(),
                              end_position=ray_end.copy(),
                              data_filename=out_tri_name,
                              lines=line_list,
                              ftype='gas',
                              fields=['metallicity', 'H_p0_number_density'])

def get_physical_info(ds, ray):
    '''
    input: simulation dataset and
    '''


def write_out(hdulist, filename='spectrum.fits'):
    print("saving fits file to .... " + filename)
    hdulist.writeto(filename, overwrite=True, output_verify='fix')
    return ""
