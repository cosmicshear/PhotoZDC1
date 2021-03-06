"""Classes and functions to interface with data sets

  

"""

import numpy as np
import astropy.io.fits as fits
#from astropy.table import Table
import pandas as pd
import operator
import difflib
import h5py

import sedMapper

# operator look up dictionary
ops = {"==": operator.eq, "!=": operator.ne, ">": operator.gt, ">=": operator.ge, "<": operator.lt,
       "<=": operator.le}
       
       
def read_fits_header(file_to_read):
    """Print some basic info from the FITS file header
    """
    
    hdulist = fits.open(file_to_read)
    
    print "HDU list info:"
    print hdulist.info(), "\n"
    
    print "Header of each HDU:"
    for hdu in hdulist:
        print repr(hdu.header), '\n'
    print ""

    print "Columns in 2nd HDU:"
    cols = hdulist[1].columns
    print cols.info(), "\n"
    print ""
        
    print "Comment(s) in first HDU"
    print hdulist[0].header['COMMENT'], "\n"
    
    hdulist.close()
    
    
def convert_df_to_fitstable(df):
    """Convert dataframe to a FITS binary table
    
       @param df  dataframe 
    """
    import re
    
    # any column ending in ID is the ID column
    reg = ".*ID$"

    fits_columns = []
    for column in df:
    
        # numpy doesn't allow a dtype with a unicode column name
        # so convert to str
        col_name = str(df[column].name)
        col_data = df[column].values
    
        # all columns double precision except for ID column
        format_column = 'D'
    
        # check for ID column
        if re.match(reg, col_name):
            col_data.astype(np.int64, copy=False)
            format_column = 'K'
    
        col = fits.Column(name=col_name, format=format_column, array=col_data)
        fits_columns.append(col)


    cols = fits.ColDefs(fits_columns)
    tbhdu = fits.BinTableHDU.from_columns(cols)
    return tbhdu
    

def add_comment_to_header(comment):
    """Create a header and add a comment to it"""
    
    prihdr = fits.Header()
    prihdr['COMMENT'] = comment
    prihdu = fits.PrimaryHDU(header=prihdr)
    
    return prihdu


def write_df_to_fits(df, outfile_name, comment=""):
    """Write a dataframe to a FITS file
    
       @param df              dataframe
       @param outfile_name    name of FITS file to create
       @param comment         comment to add to primary header
    """

    tbhdu = convert_df_to_fitstable(df)
    prihdu = add_comment_to_header(comment)
    thdulist = fits.HDUList([prihdu, tbhdu])
    thdulist.writeto(outfile_name)


class ReadCosmoSim(object):
    """Read cosmological simulation from a FITS or text file
    
       Text file must contain column names that can be parsed by numpy.genfromtxt().
       FITS file must have extension .fit or .fits
    
    """

    def __init__(self, file_to_read, nhdu=1, delimiter=' ', index=False, **kwargs):
        """Read in data from file
        
           @param file_to_read   full path and name of file containing simulation
           @param nhdu           (FITS ONLY) HDU number containing data (indexed from zero)
           @param delimiter      (TEXT ONLY) character that delimits text file
           @param index          (TEXT ONLY) column number to use as row index (default is none)
           @param kwargs         (TEXT ONLY) keyword arguments to pass to pd.read_csv
        """
        ext = file_to_read.split(".")[-1]
        
        if (ext=="fits" or ext=="fit"):
            self._filetype = "FITS"
            self._read_fits(file_to_read, nhdu)
        elif (ext=="hdf5"):
            self._filetype = "HDF5"
            self._read_hdf5(file_to_read)
        else:
            self._filetype = "TEXT"
            self._read_text(file_to_read, delimiter, index, **kwargs)


    def _read_fits(self, file_to_read, nhdu=1):
        """Read data and column names from a FITS file

           @param file_to_read   full path and name of file containing simulation
           @param nhdu           HDU number containing data (indexed from zero)
        """
        
        hdulist = fits.open(file_to_read)
        cols = hdulist[nhdu].columns.names
        data = hdulist[nhdu].data
        
        nrows = len(data)
        ncols = len(data[0])
        data_array = np.zeros((nrows, ncols))
        
        for i, row in enumerate(data):
            for j in range(len(row)):
                data_array[i,j] = row[j]
                
        self._data = pd.DataFrame(data_array, columns=cols)
        self._col_names = cols
        
        hdulist.close()
        
        # this fix now broken
        #table = Table.read(file_to_read)
        #data = table._data # will be deprecated but Table.as_array doesn't work????
        ## Fix byte order.
        ## See https://github.com/astropy/astropy/issues/1156
        #data = data.byteswap().newbyteorder()
        #self._data = pd.DataFrame.from_records(data)
        #self._col_names = self._data.columns
        
        # old attempt
        #hdulist = fits.open(file_to_read)
        #col_names = [x.name for x in hdulist[nhdu].data.columns]
        #self._data = pd.DataFrame(np.asarray(hdulist[nhdu].data), columns=col_names)
        #self._data = pd.DataFrame.from_records(np.asarray(hdulist[nhdu].data))
        #self._data.columns = col_names
        #self._col_names = self._data.columns
        # ValueError: Big-endian buffer not supported on little-endian compiler
        
        
    def _read_text(self, file_to_read, delimiter=' ', index=False, **kwargs):
        """Read data and column names from a text file

           @param file_to_read   full path and name of file containing simulation
           @param delimiter      delimiter in text file
           @param index          column to use as row index (False=none)
           @param kwargs         keyword arguments to pass to pd.read_csv
        """
        self._data = pd.read_csv(file_to_read, delimiter=delimiter, index_col=index, **kwargs)  
        #np.genfromtxt(file_to_read, dtype='float', names=True) # this is WAY slower
        self._col_names = self._data.columns


    def _read_hdf5(self, file_to_read):
        """Read hierarchical data from HDF5 file
        
           @param file_to_read   full path and name of file containing simulation
        
        """
    
        # create empty dataframe
        self._data = pd.DataFrame()
    
        # open hdf5 file
        f = h5py.File(file_to_read, 'r')

        # loop over tree structure
        ii = 0
        for zslice in f.keys():
    
            output = f[zslice]
            #print "On redshift slice", zslice ,"of", len(f.keys())
            columns = output.keys()
    
            # if at least one column in this slice
            if len(columns)>=1:      
            
                self._col_names = columns
                ncol = len(columns)
                
            
                data = []
                for i, col in enumerate(columns):
                    data.append(output[col].value)
                
                data = np.asarray(data).T
                #print len(data)
                
                #print "range from", ii, ii+len(data)
                index = range(ii, ii+len(data))
                ii = ii+len(data)
                self._data = self._data.append(pd.DataFrame(data, columns=columns, index=index))
         
        f.close()

    
    
    ### Print method
    def head(self, n=5):
        print self._data.head(n)
        

    ### Getter methods
        
    def get_number_of_cols(self):
        """Return number of columns in file
        """
        return len(self._col_names)
        
        
    def get_number_of_rows(self):
        """Return number of entries in file
        """
        return len(self._data)
        
        
    def get_dimensions(self):
        """Return the size of each dimension in the file
        """
        return self._data.shape
        
    
    def get_column_names(self):
        """Return column names
        """
        return self._col_names
        
        
    def get_column_names_containing(self, string):
        """Return list of column names that contain "string"
        
           @param string    partial string column names must containg
        """
        
        col_list = []
        for col in self._col_names:
            if string in col:
                col_list.append(col)
        
        return col_list
        
        
    def get_column(self, column, selection=None):
        """Return column via its index number or name
        
           @param column       column name (str) or index (int)
           @param selection    perform selection on column tuple describing condition on column
                               e.g. (">", 20.)
        """
        
        self._check_column_valid(column)
        
        if (selection==None):
            return self._data[column]
        else:
            condition = [(column, selection[0], selection[1])]
            return self.select_given_all_true(condition, cols_to_select=[column])
        
        
    ### Select from catalog methods
        
    # could make data selection method
    # args: cols_to_select, conditions (tuple of: (col, cond, val) e.g. (colname, '>', 10)
    #    df[ (df.a > 100) & (df.b == "test") ]
    def select_given_all_true(self, conditions, cols_to_select='all'):
        """Select all the listed columns and return all entries where all the conditions are true. Returns
           dataframe
        
           @param conditions       list of tuples describing conditions upon each column
                                   (colname/index, 'operator', value)
           @param cols_to_select   list of column names OR list of column numbers OR select all columns
          
           For example:
           select_given_all_true([("uband", "<", 21), ("redshift", ">=", 0.1)])
           select_given_all_true([("uband", "<", 21), ("redshift", ">=", 0.1)], ["ra", "dec"])
           select_given_all_true([(10, "<", 21), (1, ">=", 0.1)], [2, 3])
        """
        
        # check all the column names to return
        if isinstance(cols_to_select, list):
            for column in cols_to_select:
                self._check_column_valid(column)
        
        # make condition, start with everything true
        final_condition = pd.Series(np.ones(self._data.shape[0], dtype=bool))
        for condition in conditions:
                        
            condition_col = condition[0]
            op = condition[1]
            val = condition[2]
            
            print "Adding condition that column: ", condition_col , op , val
            final_condition = operator.and_( final_condition, ops[op](self._data[condition_col],val) )

        if isinstance(cols_to_select, list):
            return self._data[final_condition][cols_to_select]
        else:
            return self._data[final_condition]
            
            
    def group_by_column(self, column, bins):
        """Return a dataframe grouped into bins based upon a column
           
           @param column     column name (str) or index (int)
           @param bins       bin edges to be used to group the data in column
        """ 
        self._check_column_valid(column)
        
        return self._data.groupby(pd.cut(self._data[column], bins=bins))
        
        
    def group_by_color(self, column1, column2, bins):
        """Return a dataframe grouped into bins based upon a "color" (difference between two columns, doesn't
           technically HAVE to be a color)
           
           if the color = magX - magY then column1 == magX and column2 == magY
           
           @param column1    column name (str) or index (int) of bluer magnitude
           @param column2    column name (str) or index (int) of redder magnitude
           @param bins       bin edges to be used to group the data in (column
        """ 
        self._check_column_valid(column1)
        self._check_column_valid(column2)
        
        return self._data.groupby(pd.cut(self._data[column1]-self._data[column2], bins=bins))
        
        
    def get_random_subsample(self, nsample, cols_to_select='all'):
        """Return a random sub-sample of the catalog of size nsample. Returns dataframe
        
           @param nsample           number of entries of catalog to select [int]
           @param cols_to_select    list of column names OR list of column numbers OR select all columns
        """
        
        # check all the column names to return
        if isinstance(cols_to_select, list):
            for column in cols_to_select:
                self._check_column_valid(column)
                
        ids = np.random.permutation(self.get_number_of_rows())[:nsample]
        if isinstance(cols_to_select, list):
            return self._data.iloc[ids][cols_to_select]
        else:
            return self._data.iloc[ids]
        
        
    def get_array_of_colors(self, mag_columns, filter_names=None, nsample=None):
        """Return pd dataframe of colors by subtracting magnitude columns in order supplied. 
        
           @param mag_columns     names of columns containing magnitudes. Must be supplied in correct order
                                  so color1 = mag_col1 - mag_col2
                                     color2 = mag_col2 - mag_col3 etc
           @param filter_names    if supplied renames columns of data frame according to names in filter_names
                                  MUST MATCH ORDER OF MAG_COLUMNS
           @param nsample         number of entries from table to select, if less than table size, randomly
                                  selects the entries
                                  
           Returns: 
           - dataframe of colors for each galaxy in sample, column names are colors
           
        """
        
        # data to use (either full dataset or random subsample of size nsample)
        data, nsample = self._get_data(nsample)
            
            
        # Check the columns are valid
        self._check_all_columns(mag_columns, filter_names)
        
        
        # Just return color dataframe
        return self._get_colors(data, mag_columns, filter_names, nsample)
        
        
    ### SEDMAPPER 
    
    def return_matched_catalog(self, mag_columns, filter_names, sed_colors, nsample=None, nstd=3., tol=1):
        """ 
           @param mag_columns     names of columns containing magnitudes. Must be supplied in correct order
                                  so color1 = mag_col1 - mag_col2
                                     color2 = mag_col2 - mag_col3 etc
           @param filter_names    if supplied renames columns of data frame according to names in filter_names
                                  MUST MATCH ORDER OF MAG_COLUMNS
           @param nsample         number of entries from table to select, if less than table size, randomly
                                  selects the entries
           @param nstd            Number of standard deviations SED color must be within mean of galaxy
                                  colors to be considered a "good" match
           
           @param tol             Tolerance: minimum number of SEDs a particular color must have a "good"
                                  match with to be included in the mapping
           
                                  """
  
        # data to use (either full dataset or random subsample of size nsample)
        data, nsample = self._get_data(nsample)

 
        # Check the columns are valid
        self._check_all_columns(mag_columns, filter_names)
        
        
        # Get color dataframe to work with
        print nsample, len(mag_columns)-1
        color_array = self._get_colors(data, mag_columns, filter_names, nsample)


        # Check match between galaxy colors and SEDs
        # poor_matches is a list of SEDs, one for each color. Any SEDs in each list are defined to be
        # a "poor" match to the color, i.e. the SED color is not within mean[color]+/-nstd*std[color]
        # of the simulated galaxies
        poor_matches = sedMapper.check_color_match(color_array, sed_colors, nstd)
        
        
        # Find closest SED match to each galaxy, each color must have a minimum number=tol of SEDs 
        # that are an OK match
        sed_label = sedMapper.perform_color_match(color_array, sed_colors, poor_matches, tol)
        
        
        # Add column of labels to data
        data['sed_label'] = sed_label.tolist()
        
        # return data and color dataframes
        return data, color_array
        
        
    ### Helper methods
    
    def _get_colors(self, data, mag_columns, filter_names, nsample):
        """Return dataframe of colors, if given, substitute column name for filter name  """
        
        color_array = np.zeros((nsample, len(mag_columns)-1))
        color_names = []
        
        for i in range(len(mag_columns)-1):
        
            # calc galaxy color: simply data in mag_columns[i]-mag_columns[i+1]
            color_array[:,i] = data[mag_columns[i]] - data[mag_columns[i+1]]
            
            # if filter_names supplied, replace magnitude column name with filter name
            if (filter_names != None):
                color_names.append(str(filter_names[i]) + "-" + str(filter_names[i+1]) )
            else:
                color_names.append(str(mag_columns[i]) + "-" + str(mag_columns[i+1]) )
        
        # convert to dataframe and return
        return pd.DataFrame(color_array, columns=color_names)
        

    def _get_data(self, nsample):
        """Get random realisation of data in dataframe, or full dataset"""
        
        if (nsample==None):
            nsample = self.get_number_of_rows()
        
        if (nsample<self.get_number_of_rows()):
            data = self.get_random_subsample(nsample)
        else:
            data = self._data
            
        return data, nsample
        
        
    def _check_all_columns(self, mag_columns, filter_names):
        """Check all names of columns containing magnitudes actually exist in the catalog 
        
           @param mag_columns   names of columns containing magnitudes
           @param filter_names  names of the filters corresponding to the magnitudes 
           
           order of the above two lists must be the same!
           If filter_names==None it is ignored
        """
        
        if (filter_names != None):
        
            # checksum on number of filters vs number of columns
            if ( len(filter_names) != len(mag_columns) ):
                msg = "ERROR! column number (" + str(len(mag_columns)) + ") and "
                msg +="filter number (" + str(len(filter_names)) + ") don't match"
                raise ValueError(msg)
        
            # check all the columns to return (also visually that they match the filter names!)
            for column, filt in zip(mag_columns, filter_names):
                print "col =", column ,"filter =", filt ,"match??"
                self._check_column_valid(column)
        else:
        
            for column in mag_columns:
                self._check_column_valid(column)
                
        
    def _check_column_valid(self, column):
        """Check the column name or index is valid
           
           @param column    column name (str) or index (int)
        """
        if (isinstance(column, (int, long) )):
            if (column<0 and column>=self.get_number_of_cols()):
                raise ValueError("ERROR! column number (" + str(column) + ") not valid!")
                
        if (isinstance(column, str )):
            if (column not in self._col_names):
                raise ValueError("ERROR! column name (" + column + ") not valid!")
                
            
def split_training(training_file, outroot, pct_valid=0.2, redshift_column="redshift"):
    """Split FITS file with training data into two separate FITS files of
       training data and validation data
       
       @param training_file     FITS file containing training data
       @param outroot           output root of new files
       @param pct_valid         percent of training data to be put in validation set
       @param redshift_column   column name of FITS file containing redshifts
    """
    
    # read FITS into dataframe
    training_data = ReadCosmoSim(training_file)
    training_df = training_data._data
    
    # remove the redshift column from a list of the columns
    cols = list(training_df.columns.values)
    cols.remove(redshift_column)
    
    from sklearn import cross_validation

    # split into training and testing
    phot_train, phot_test, redshift_train, redshift_test = cross_validation.train_test_split(
    training_df[cols], training_df[redshift_column], test_size=pct_valid, random_state=0)
    
    # rejoin the phot data and the redshift data back together
    training_set = phot_train.join(redshift_train)
    validation_set = phot_test.join(redshift_test)
    
    # write files 
    comment = "pure training sample extracted from " + training_file
    write_df_to_fits(training_set, outroot+"_puretrain.fits", comment)
    
    comment = "validation sample extracted from " + training_file
    write_df_to_fits(validation_set, outroot+"_validation.fits", comment)
    
            
# would like to develop this method
# however it doesn't quite work because for some reason:
# with "SDSS_u" difflib.get_close_matches thinks
# 'SDSS_z_Absolute' is closer a match than 'SDSS_u_Absolute'
# edit distance algos don't seem to work right either?

#def mapNames(adopted_names, alt_names, match_quality):
#    """Create dictionary mapping "adopted" names (e.g. name of filter) to "alternate" name (e.g. name of 
#       column in catalog containing magnitudes in the corresponding filter) 
#    
#       @param adopted_names   "adopted" or "offical" name of some quantity
#       @param alt_names       "alternate" name for the same quantity
#       @param match_quality   between 0 and 1, want to keep this low as names will be fairly different
#    """
#    
#    for name in alt_names:
#        difflib.get_close_matches(name, adopted_names, 1, match_quality)
#        

def orderMagnitudeColumns(filter_order, map_filtname_to_colname):
    """Given order of filters supplied, and mapping between filter names and column names, 
       return a list of the column names in the same order as the filters
    """
     
    column_filter = []
    for filt in filter_order:
        column_filter.append(map_filtname_to_colname[filt])
        
    return column_filter
    

def add_colors_to_df(df, mag_columns):
    """Add colors to the dataframe
       
       @param df             dataframe
       @param mag_columns    column names containing magnitudes
    """

    ncolor = len(mag_columns)-1
    for i in range(ncolor):
        color_name = mag_columns[i] + "-" + mag_columns[i+1]
        
        # add color column to dust simulation
        df[color_name] = df[mag_columns[i]] - df[mag_columns[i+1]]
        
        
